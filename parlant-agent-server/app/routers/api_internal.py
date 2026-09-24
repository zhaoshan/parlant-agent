"""/api/internal/* —— 面向 parlant-agent-runtime 的内部端点（不面向前端）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/internal", tags=["internal"])


@router.get("/published-agents")
async def published_agents(request: Request) -> dict[str, Any]:
    """runtime 启动拉取：返回全部 published 定义的 agent_id/version/definition。"""
    docs = await request.app.state.agent_repository.list_published()
    return {
        "agents": [
            {"agent_id": d["agent_id"], "version": d["version"], "definition": d["definition"]}
            for d in docs
        ]
    }