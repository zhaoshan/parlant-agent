"""/api/agents/* —— Agent 定义 CRUD / 版本 / 发布编排（server 独占写定义层）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from httpx import HTTPStatusError

from app.authz import (
    AGENT_BUILD,
    AGENT_DELETE,
    AGENT_PUBLISH,
    AGENT_READ,
    AuthorizationContext,
    require,
)
from app.models import JourneyLayoutSave, PublishBody, RollbackBody
from app.services import PublishError

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _svc(request: Request) -> Any:
    return request.app.state.agent_service


@router.get("")
async def list_agents(
    request: Request, ctx: AuthorizationContext = Depends(require(AGENT_READ))
) -> dict[str, Any]:
    return {"agents": await _svc(request).list_agents()}


@router.post("")
async def create_agent(
    request: Request,
    ctx: AuthorizationContext = Depends(require(AGENT_BUILD)),
    strict: bool = False,
) -> dict[str, Any]:
    data = await request.json()
    try:
        # created_by 回填已认证用户（doc16 §4.1），不再硬编码 "api"
        return await _svc(request).save(data, created_by=ctx.user_id, strict=strict)
    except ValueError as exc:
        raise HTTPException(status_code=409 if strict else 422, detail=str(exc)) from exc


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    request: Request,
    version: str | None = None,
    ctx: AuthorizationContext = Depends(require(AGENT_READ)),
) -> dict[str, Any]:
    doc = await _svc(request).get(agent_id, version)
    if not doc:
        raise HTTPException(status_code=404, detail=f"agent '{agent_id}' 不存在")
    return doc


@router.get("/{agent_id}/versions")
async def list_versions(
    agent_id: str,
    request: Request,
    ctx: AuthorizationContext = Depends(require(AGENT_READ)),
) -> dict[str, Any]:
    versions = await _svc(request).list_versions(agent_id)
    if not versions:
        raise HTTPException(status_code=404, detail=f"agent '{agent_id}' 不存在")
    return {"agent_id": agent_id, "versions": versions}


# ---------- 旅程流程图布局（纯 UI 连线挂载点；独立于定义层，不脏草稿/不进版本） ----------

@router.get("/{agent_id}/journeys/{journey_id}/layout")
async def get_journey_layout(
    agent_id: str,
    journey_id: str,
    request: Request,
    ctx: AuthorizationContext = Depends(require(AGENT_READ)),
) -> dict[str, Any]:
    doc = await request.app.state.journey_layout_repository.get(agent_id, journey_id)
    return doc or {"agent_id": agent_id, "journey_id": journey_id, "edges": {}}


@router.put("/{agent_id}/journeys/{journey_id}/layout")
async def save_journey_layout(
    agent_id: str,
    journey_id: str,
    body: JourneyLayoutSave,
    request: Request,
    ctx: AuthorizationContext = Depends(require(AGENT_BUILD)),
) -> dict[str, Any]:
    # pydantic 模型 → 纯 dict（Motor 不能编码 BaseModel；None 字段不存，读回即缺省=自动）
    edges = {k: v.model_dump(exclude_none=True) for k, v in body.edges.items()}
    nodes = {k: v.model_dump() for k, v in body.nodes.items()}
    # MongoDB 键名禁止 NUL 字节：显式 422，避免落到 BSON 编码层报 500
    if any(chr(0) in k for k in edges) or any(chr(0) in k for k in nodes):
        raise HTTPException(status_code=422, detail="edges/nodes 键不能包含 NUL/控制字符")
    return await request.app.state.journey_layout_repository.save(agent_id, journey_id, edges, nodes)


@router.post("/{agent_id}/publish")
async def publish_agent(
    agent_id: str,
    body: PublishBody,
    request: Request,
    ctx: AuthorizationContext = Depends(require(AGENT_PUBLISH)),
) -> dict[str, Any]:
    try:
        return await _svc(request).publish(agent_id, body.version)
    except PublishError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.post("/{agent_id}/rollback")
async def rollback_agent(
    agent_id: str,
    body: RollbackBody,
    request: Request,
    ctx: AuthorizationContext = Depends(require(AGENT_DELETE)),
) -> dict[str, Any]:
    try:
        return await _svc(request).rollback(agent_id, body.version)
    except PublishError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


@router.delete("/{agent_id}/versions/{version}")
async def delete_version(
    agent_id: str,
    version: str,
    request: Request,
    ctx: AuthorizationContext = Depends(require(AGENT_DELETE)),
) -> dict[str, Any]:
    """物理删除单个版本（清理多余 draft / 历史版本）；不能删当前 published。"""
    return await _svc(request).delete_version(agent_id, version)


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    request: Request,
    ctx: AuthorizationContext = Depends(require(AGENT_DELETE)),
) -> dict[str, Any]:
    """停用：卸载 runtime 引擎实体（定义版本仍保留在库）。"""
    try:
        ok = await _svc(request).unload(agent_id)
    except HTTPStatusError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"agent '{agent_id}' 未加载") from exc
        raise HTTPException(status_code=502, detail=f"停用失败：{exc.response.text[:300] if exc.response else exc}") from exc
    except Exception as exc:  # noqa: BLE001 - runtime 不可达等
        raise HTTPException(status_code=502, detail=f"停用失败：{exc}") from exc
    if not ok:
        raise HTTPException(status_code=404, detail=f"agent '{agent_id}' 未加载")
    return {"agent_id": agent_id, "unloaded": True}


@router.delete("/{agent_id}/delete")
async def delete_agent_logical(
    agent_id: str,
    request: Request,
    ctx: AuthorizationContext = Depends(require(AGENT_DELETE)),
) -> dict[str, Any]:
    """逻辑删除 Agent：卸载运行时 + 打删除墓碑，定义保留在 Mongo（可恢复）。"""
    return await _svc(request).delete_agent(agent_id)