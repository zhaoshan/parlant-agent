"""面向 parlant-agent-runtime 的**内部端点**（agent 相关，不面向前端）。

server↔runtime 内部通信专用子包：当前只有「拉取全部 published 定义」一个端点
（runtime 启动时调用）；未来 runtime→server 的其他内部能力在同一子包扩展。

端点 prefix 统一 `/api/internal`，与对外路由（`app/routers/` 顶层 agents/sessions/...）隔离。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/internal", tags=["internal"])


@router.get("/published-agents")
async def list_published_agents(request: Request) -> dict[str, Any]:
    """runtime 启动拉取：返回全部 published 定义的 agent_id/version/definition。"""
    docs = await request.app.state.agent_repository.list_published()
    return {
        "agents": [
            {"agent_id": d["agent_id"], "version": d["version"], "definition": d["definition"]}
            for d in docs
        ]
    }
