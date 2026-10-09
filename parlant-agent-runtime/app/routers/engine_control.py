"""runtime 引擎控制面（原 internal_api）：`/internal/*` API，只面向 parlant-agent-server，不面向前端。

server（BFF）驱动 runtime 引擎的入口，端点：
    POST   /internal/agents/{id}/load    接收完整定义 JSON，幂等热加载进引擎
    POST   /internal/agents/{id}/unload  卸载引擎实体（含子实体，级联清理）
    GET    /internal/agents              已加载 agent 列表 + 加载状态
    GET    /internal/health              引擎健康（供 server 探活/选主）

原定义 CRUD/版本/发布/回滚端点已下线（迁至 server `/api/agents/*`，见 plan 阶段3 任务 3.2）。
"""

from __future__ import annotations

import os
from importlib import metadata
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from parlant.core.context_variables import ContextVariableStore

from app.config import get_settings
from app.models import parse_definition
from app.services import get_runtime


def _pkg_version(name: str) -> str:
    try:
        return metadata.version(name)
    except Exception:  # noqa: BLE001 - 未安装/元数据缺失时降级
        return "?"


def require_internal_token(request: Request) -> None:
    """`/internal/*` 服务间鉴权（doc09 §4.4）：校验 X-Internal-Token（与 server .env 同值）。

    未配置 → 503 fail-closed（防止引擎控制面/变量覆盖被直调）；token 不符 → 401。
    """
    settings = get_settings()
    expected = settings.internal_token
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="runtime 未配置 INTERNAL_TOKEN：/internal/* 已禁用以防未鉴权暴露（doc09 §4.4）",
        )
    if request.headers.get("X-Internal-Token") != expected:
        raise HTTPException(status_code=401, detail="无效的 X-Internal-Token")


async def configure_internal_api(app: FastAPI) -> None:
    # 注意：configure_api 在 p.Server.__aenter__ 内（create_api_app 阶段）被调用，
    # 彼时 init_runtime() 尚未执行；故 get_runtime() 必须延迟到请求期（此时 HTTP 服务
    # 已在 __aexit__ 启动，runtime 必然就绪）。

    @app.get("/internal/agents", dependencies=[Depends(require_internal_token)])
    async def list_loaded_agents() -> dict[str, Any]:
        rt = get_runtime()
        return {"agents": [{"agent_id": a, "loaded": True} for a in rt.registry.list()]}

    @app.post("/internal/agents/{agent_id}/load", dependencies=[Depends(require_internal_token)])
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

    @app.post("/internal/agents/{agent_id}/unload", dependencies=[Depends(require_internal_token)])
    async def unload_agent(agent_id: str) -> dict[str, Any]:
        """卸载引擎实体（含子实体级联清理）；未加载返回 404。"""
        ok = await get_runtime().registry.unload(agent_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"agent '{agent_id}' 未加载")
        return {"agent_id": agent_id, "unloaded": True}

    @app.post("/internal/agents/{agent_id}/variables/override", dependencies=[Depends(require_internal_token)])
    async def override_variables(agent_id: str, request: Request) -> dict[str, Any]:
        """按**客户维度**覆盖该已加载 agent 实例的 Context Variable 值。

        引擎变量 id 由 SDK 随机生成（定义层 `var_*` 只是标签），故按**变量名**解析：
        在已加载实例的 `list_variables()` 里 name → id，再 `update_value(variable_id,
        key=customer_id, data=value)`（key=customer.id 优先级最高，覆盖 Agent 构建默认；
        同 customer 的所有会话共享该值 → 模拟对话换身份互不干扰）。

        引擎 `update_value` 按 (variable_id, key) **upsert**，变量名未找到只记 missing 不报错。
        """
        rt = get_runtime()
        agent = rt.registry.get(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"agent '{agent_id}' 未加载")
        payload = await request.json()
        customer_id = str(payload.get("customer_id") or "")
        if not customer_id:
            raise HTTPException(status_code=422, detail="缺少 customer_id")
        variables = payload.get("variables") or {}
        if not isinstance(variables, dict):
            raise HTTPException(status_code=422, detail="variables 必须是 {name: value} 对象")

        store = rt.server.container[ContextVariableStore]
        by_name = {v.name: v for v in await agent.list_variables()}
        applied: dict[str, str] = {}
        missing: list[str] = []
        for name, value in variables.items():
            var = by_name.get(str(name))
            if var is None:
                missing.append(str(name))
                continue
            await store.update_value(variable_id=var.id, key=customer_id, data=value)
            applied[str(name)] = var.id
        return {"agent_id": agent_id, "customer_id": customer_id, "applied": applied, "missing": missing}

    @app.get("/internal/health", dependencies=[Depends(require_internal_token)])
    async def internal_health() -> dict[str, Any]:
        return {"status": "ok", "service": "parlant-agent-runtime"}

    @app.get("/internal/info", dependencies=[Depends(require_internal_token)])
    async def internal_info() -> dict[str, Any]:
        """运行时信息（供设置页等 UI 展示模型/版本，不含敏感凭据）。"""
        return {
            "service": "parlant-agent-runtime",
            "parlant_version": _pkg_version("parlant"),
            "main_llm_model": os.getenv("LITELLM_PROVIDER_MODEL_NAME") or "未配置",
            "embedding_model": os.getenv("LITELLM_EMBEDDING_MODEL_NAME") or "未配置",
        }