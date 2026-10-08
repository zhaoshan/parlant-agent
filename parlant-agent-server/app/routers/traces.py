"""/api/traces/* —— 链路历史数据代理（langfuse 取数，阶段3/4 web 链路历史 tab）。

设计（对照 web 链路历史 tab 页面设计）：
- 本服务**代理 langfuse 公开 API**（Observations API v2），密钥只在服务端，
  前端无需持凭证。
- `GET /api/traces/{trace_id}`：返回该 trace 的 observation **扁平数组**
  （含 parentObservationId），由前端组装执行链路树（左树 + 右节点详情）。
- 错误语义：
    503  langfuse 未配置（.env 缺 LANGFUSE_*）
    502  langfuse 不可达 / 鉴权失败等下游错误
    404  langfuse 无该 trace 的 observation
- 网络约定：LangfuseClient 内部 `trust_env=False` 直连（见其模块注释）。
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from app.authz import TRACE_READ, AuthorizationContext, require

traces_router = APIRouter(prefix="/api/traces", tags=["traces"])


def _lf(request: Request) -> Any:
    return request.app.state.langfuse_client


@traces_router.get("/{trace_id}")
async def get_trace(
    trace_id: str,
    request: Request,
    ctx: AuthorizationContext = Depends(require(TRACE_READ)),
) -> dict[str, Any]:
    """拉取一个 trace 的全部 observation（扁平数组，前端组树）。"""
    client = _lf(request)
    if not client.configured:
        raise HTTPException(
            status_code=503,
            detail="langfuse 未配置：请在 server .env 配置 LANGFUSE_BASE_URL / PUBLIC_KEY / SECRET_KEY",
        )
    try:
        observations = await client.get_trace_observations(trace_id)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else 502
        body = (exc.response.text or "")[:300]
        raise HTTPException(
            status_code=502,
            detail=f"langfuse 读取失败（HTTP {status}）：{body or exc}",
        ) from exc
    except Exception as exc:  # noqa: BLE001 - 见 _map
        raise HTTPException(status_code=502, detail=f"langfuse 不可达：{exc}") from exc

    if not observations:
        raise HTTPException(status_code=404, detail="langfuse 未找到该 trace 的链路数据")
    return {"trace_id": trace_id, "observations": observations}
