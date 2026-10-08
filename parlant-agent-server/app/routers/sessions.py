"""/api/sessions/* 与 /api/customers/* —— 会话代理 + SSE 透传（阶段3.3）。

设计（对照 docs/03-production/08-内置ChatUI与HTTP接口分析.md）：
- 本服务不实现会话逻辑，只**代理** Parlant REST（runtime）：
    POST /api/sessions                  -> runtime POST /sessions            + 落 MySQL 台账
    GET  /api/sessions?user_id=         -> 读 MySQL 台账（按用户查列表，3.4/3.10）
    GET  /api/sessions/{id}             -> runtime GET /sessions/{id}        + 台账字段
    POST /api/sessions/{id}/events      -> runtime POST /sessions/{id}/events
    GET  /api/sessions/{id}/events      -> runtime SSE（sse=true）逐帧透传
    POST /api/customers                 -> runtime POST /customers
    GET  /api/customers                 -> runtime GET /customers
- 错误透传：runtime 4xx/5xx 原样映射，网络错误统一 502。
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.authz import (
    CUSTOMER_MANAGE,
    SESSION_READ,
    SESSION_SEND,
    AuthorizationContext,
    require,
)
from app.models import CustomerCreateBody, SessionCreateBody

sessions_router = APIRouter(prefix="/api/sessions", tags=["sessions"])
customers_router = APIRouter(prefix="/api/customers", tags=["customers"])


def _svc(request: Request) -> Any:
    return request.app.state.session_service


def _map_http_error(exc: Exception, fallback: str = "转发失败") -> HTTPException:
    """把 httpx 下游错误映射为 HTTP 异常（404 透传，其余 502）。"""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else 502
        body = exc.response.text[:300] if exc.response is not None else str(exc)
        return HTTPException(status_code=status, detail=body or fallback)
    return HTTPException(status_code=502, detail=f"{fallback}：{exc}")


@customers_router.post("")
async def create_customer(
    body: CustomerCreateBody,
    request: Request,
    ctx: AuthorizationContext = Depends(require(CUSTOMER_MANAGE)),
) -> dict[str, Any]:
    try:
        return await _svc(request).create_customer(
            body.name, body.id, body.metadata, body.tags
        )
    except Exception as exc:  # noqa: BLE001 - 见 _map_http_error
        raise _map_http_error(exc, "创建客户失败") from exc


@customers_router.get("")
async def list_customers(
    request: Request,
    ctx: AuthorizationContext = Depends(require(CUSTOMER_MANAGE)),
) -> dict[str, Any]:
    try:
        customers = await _svc(request).list_customers()
    except Exception as exc:  # noqa: BLE001
        raise _map_http_error(exc, "拉取客户列表失败") from exc
    return {"customers": customers}


@sessions_router.post("")
async def create_session(
    body: SessionCreateBody,
    request: Request,
    ctx: AuthorizationContext = Depends(require(SESSION_SEND)),
) -> dict[str, Any]:
    """创建会话：转发 runtime + 落 MySQL 台账（source 标记渠道；mode=draft 用独立 @draft 实例试跑草稿）。"""
    if not body.customer_id:
        raise HTTPException(status_code=422, detail="创建会话需要 customer_id（可先 POST /api/customers 建客户，或用内置 guest）")
    try:
        return await _svc(request).create_session(
            body.agent_id,
            body.customer_id,
            # user_id 未由前端显式传时，回填已认证用户（doc16 §4.1）
            user_id=body.user_id or ctx.user_id,
            title=body.title,
            source=body.source,
            mode=body.mode,
            variables=body.variables,
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_http_error(exc, "创建会话失败") from exc


@sessions_router.get("")
async def list_sessions(
    request: Request,
    user_id: str | None = None,
    agent_id: str | None = None,
    source: str | None = None,
    session_id: str | None = None,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
    ctx: AuthorizationContext = Depends(require(SESSION_READ)),
) -> dict[str, Any]:
    """会话列表（MySQL 台账，含有效性/来源渠道；条件可空，默认查全量）。

    `session_id`：按会话 id 模糊匹配；`status`：active=进行中 / ended=已结束。
    """
    return await _svc(request).list_sessions(
        user_id=user_id,
        agent_id=agent_id,
        source=source,
        session_id_like=session_id,
        status_filter=status,
        limit=limit,
        offset=offset,
    )


@sessions_router.post("/{session_id}/close")
async def close_session(
    session_id: str,
    request: Request,
    ctx: AuthorizationContext = Depends(require(SESSION_SEND)),
) -> dict[str, Any]:
    """客户/用户主动关闭会话（台账标记正常结束）。"""
    return await _svc(request).close_session(session_id, reason="normal")


@sessions_router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    request: Request,
    ctx: AuthorizationContext = Depends(require(SESSION_SEND)),
) -> dict[str, Any]:
    """删除会话台账 + 消息历史（前端列表删除）。"""
    return await _svc(request).delete_session(session_id)


@sessions_router.get("/{session_id}")
async def get_session(
    session_id: str,
    request: Request,
    ctx: AuthorizationContext = Depends(require(SESSION_READ)),
) -> dict[str, Any]:
    try:
        return await _svc(request).get_session(session_id)
    except Exception as exc:  # noqa: BLE001
        raise _map_http_error(exc, "获取会话详情失败") from exc


@sessions_router.post("/{session_id}/events")
async def post_event(
    session_id: str,
    request: Request,
    ctx: AuthorizationContext = Depends(require(SESSION_SEND)),
) -> dict[str, Any]:
    """转发发消息/事件（body 原样透传 runtime，如 {kind,source,message}）。

    前端生成 `request_id`（uuid）随请求传入 → 注入事件 metadata（随事件留存 runtime），
    server 侧据此落**消息级历史**（session_messages）并给 Agent 回复关联同一 request_id。
    用 **query 参数**传 `request_id / user_id / user_name`（URL 编码 UTF-8，避免 header 中文乱码）；
    兼容回退读同名 header。
    """
    payload = await request.json()
    q = request.query_params
    req_id = q.get("request_id") or request.headers.get("X-Request-Id")
    user_id = q.get("user_id") or request.headers.get("X-User-Id")
    user_name = q.get("user_name") or request.headers.get("X-User-Name")
    if req_id or user_id or user_name:
        meta = payload.setdefault("metadata", {})
        if not isinstance(meta, dict):
            meta = payload["metadata"] = {}
        if req_id:
            meta["request_id"] = req_id
        if user_id:
            meta["user_id"] = user_id
        if user_name:
            meta["user_name"] = user_name
    try:
        return await _svc(request).post_event(session_id, payload)
    except Exception as exc:  # noqa: BLE001
        raise _map_http_error(exc, "发送事件失败") from exc


@sessions_router.get("/{session_id}/messages")
async def list_messages(
    session_id: str,
    request: Request,
    ctx: AuthorizationContext = Depends(require(SESSION_READ)),
) -> dict[str, Any]:
    """查消息级历史（session_messages）；可选按 request_id 过滤。"""
    request_id = request.query_params.get("request_id")
    return await _svc(request).get_messages(session_id, request_id)


@sessions_router.get("/{session_id}/events")
async def stream_events(
    session_id: str,
    request: Request,
    ctx: AuthorizationContext = Depends(require(SESSION_READ)),
) -> StreamingResponse:
    """SSE 透传：订阅 runtime `sse=true` 事件流，逐块转发给 web（EventSource）。

    runtime 在 wait_for_data 内无新事件会自行关闭流，web 端 EventSource 自动重连；
    断线后按 min_offset 续传（前端传回最后消费的 offset）。
    **旁路记录**：解析 `data:` 帧，对 ai_agent 消息事件落 session_messages
    （首条插入、完成更新，带 trace_id）；透传字节原样不改。
    """
    params = dict(request.query_params)
    min_offset = int(params.get("min_offset") or 0)
    wait_for_data = int(params.get("wait_for_data") or 60)
    source = params.get("source")
    kinds = params.get("kinds")

    service = _svc(request)

    async def _relay_with_recording() -> Any:
        buf = b""
        async for chunk in service.stream_events(
            session_id,
            min_offset=min_offset,
            wait_for_data=wait_for_data,
            source=source,
            kinds=kinds,
        ):
            buf += chunk
            # SSE 帧以空行分隔（data: {...}\n\n）；边攒边切
            while b"\n\n" in buf:
                frame, buf = buf.split(b"\n\n", 1)
                if frame:
                    await _maybe_record_frame(service, session_id, frame)
                    yield frame + b"\n\n"
        if buf.strip():
            await _maybe_record_frame(service, session_id, buf)
            yield buf

    return StreamingResponse(
        _relay_with_recording(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


async def _maybe_record_frame(service: Any, session_id: str, frame: bytes) -> None:
    """解析单帧 `data: {json}`，若是 ai_agent 消息事件则落消息历史；任何失败不阻断透传。"""
    try:
        text = frame.decode("utf-8", errors="replace")
        data_payload = None
        for line in text.splitlines():
            if line.startswith("data:"):
                data_payload = line[5:].strip()
                break
        if not data_payload:
            return
        import json

        event = json.loads(data_payload)
        if event.get("kind") != "message" or event.get("source") != "ai_agent":
            return
        await service.record_agent_message(session_id, event)
    except Exception as exc:  # noqa: BLE001 - 旁路记录失败不影响 SSE 透传
        print(f"[api-sessions] 消息记录旁路失败 session={session_id}: {type(exc).__name__} {exc}")
