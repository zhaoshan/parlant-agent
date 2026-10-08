"""/api/settings —— 平台级设置与运行时信息（web 设置页数据源）。

只读聚合：runtime 模型/版本（代理 `/internal/info`，不可达时降级）+ langfuse 接入状态。
注意：LLM/向量模型真实来源是 runtime 进程的环境变量（LITELLM_PROVIDER_* / LITELLM_EMBEDDING_*），
本服务只是转发，不参与模型调用。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from app.authz import SETTINGS_READ, AuthorizationContext, require
from app.config import get_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _runtime(request: Request) -> Any:
    return request.app.state.runtime_client


@router.get("")
async def settings(
    request: Request,
    ctx: AuthorizationContext = Depends(require(SETTINGS_READ)),
) -> dict[str, Any]:
    cfg = get_settings()
    runtime: dict[str, Any] | None = None
    runtime_unreachable = False
    try:
        runtime = await _runtime(request).runtime_info()
    except Exception:  # noqa: BLE001 - runtime 未启动/网络问题，降级为未达
        runtime_unreachable = True
    return {
        "runtime": runtime,
        "runtime_unreachable": runtime_unreachable,
        "langfuse": {
            "configured": bool(
                cfg.langfuse_base_url and cfg.langfuse_public_key and cfg.langfuse_secret_key
            ),
            "base_url": cfg.langfuse_base_url,
        },
    }