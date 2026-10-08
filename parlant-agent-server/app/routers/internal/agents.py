"""面向 parlant-agent-runtime 的**内部端点**（agent 相关，不面向前端）。

server↔runtime 内部通信专用子包：当前只有「拉取全部 published 定义」一个端点
（runtime 启动时调用）；未来 runtime→server 的其他内部能力在同一子包扩展。

端点 prefix 统一 `/api/internal`，与对外路由（`app/routers/` 顶层 agents/sessions/...）隔离。
鉴权：此处是**服务间信任**（doc16 §4.4），校验 `X-Internal-Token`（与 runtime 侧同值），
不面向前端用户；server 顶层 AuthzMiddleware 已放行 `/api/internal/*`（不混入用户鉴权）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import get_settings

router = APIRouter(prefix="/api/internal", tags=["internal"])


def require_internal_token(request: Request) -> None:
    """校验 runtime 调用方的 X-Internal-Token（服务间信任；未配置则拒绝以防裸奔）。"""
    settings = get_settings()
    expected = settings.internal_token
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="server 未配置 INTERNAL_TOKEN：内部端点在未配置鉴权下已禁用（doc16 §4.4）",
        )
    if request.headers.get("X-Internal-Token") != expected:
        raise HTTPException(status_code=401, detail="无效的 X-Internal-Token")


@router.get("/published-agents", dependencies=[Depends(require_internal_token)])
async def list_published_agents(request: Request) -> dict[str, Any]:
    """runtime 启动拉取：返回全部 published 定义的 agent_id/version/definition。"""
    docs = await request.app.state.agent_repository.list_published()
    return {
        "agents": [
            {"agent_id": d["agent_id"], "version": d["version"], "definition": d["definition"]}
            for d in docs
        ]
    }
