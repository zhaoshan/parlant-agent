"""阶段3.2：runtime /internal/* API（只面向 parlant-agent-server，不面向前端）。

定义层已归 parlant-agent-server 独占写；本节只保留**执行类**端点：
    POST   /internal/agents/{id}/load    接收完整定义 JSON，幂等热加载进引擎
    POST   /internal/agents/{id}/unload  卸载引擎实体（含子实体，级联清理）
    GET    /internal/agents              已加载 agent 列表 + 加载状态
    GET    /internal/health              引擎健康（供 server 探活/选主）

原定义 CRUD/版本/发布/回滚端点已下线（迁至 server `/api/agents/*`，见 plan 阶段3 任务 3.2）。
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request

from app.models import parse_definition
from app.services import get_runtime


async def configure_internal_api(app: FastAPI) -> None:
    # 注意：configure_api 在 p.Server.__aenter__ 内（create_api_app 阶段）被调用，
    # 彼时 init_runtime() 尚未执行；故 get_runtime() 必须延迟到请求期（此时 HTTP 服务
    # 已在 __aexit__ 启动，runtime 必然就绪）。

    @app.get("/internal/agents")
    async def list_loaded_agents() -> dict[str, Any]:
        rt = get_runtime()
        return {"agents": [{"agent_id": a, "loaded": True} for a in rt.registry.list()]}

    @app.post("/internal/agents/{agent_id}/load")
    async def load_agent(agent_id: str, request: Request) -> dict[str, Any]:
        """接收完整定义 JSON，热加载进引擎（幂等：已存在则先卸载再重建）。

        兼容两种 body：原始定义 JSON，或 server 侧的 {"definition": {...}} 包裹。
        """
        rt = get_runtime()
        payload = await request.json()
        data = payload.get("definition", payload) if isinstance(payload, dict) else payload
        try:
            definition = parse_definition(data)
        except Exception as exc:  # pydantic.ValidationError
            raise HTTPException(status_code=422, detail=f"定义校验失败：{exc}") from exc
        if definition.agent.id != agent_id:
            raise HTTPException(
                status_code=422,
                detail=f"定义 agent.id({definition.agent.id}) 与路径 {agent_id} 不一致",
            )
        try:
            agent = await rt.registry.load(definition)
        except Exception as exc:  # noqa: BLE001 - 引擎装配失败
            raise HTTPException(status_code=500, detail=f"加载失败：{exc}") from exc
        return {"agent_id": agent_id, "loaded_agent": agent.id}

    @app.post("/internal/agents/{agent_id}/unload")
    async def unload_agent(agent_id: str) -> dict[str, Any]:
        """卸载引擎实体（含子实体级联清理）；未加载返回 404。"""
        ok = await get_runtime().registry.unload(agent_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"agent '{agent_id}' 未加载")
        return {"agent_id": agent_id, "unloaded": True}

    @app.get("/internal/health")
    async def internal_health() -> dict[str, Any]:
        return {"status": "ok", "service": "parlant-agent-runtime"}