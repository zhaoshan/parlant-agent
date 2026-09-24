"""configure_api 扩展：在 Parlant 的 FastAPI app 上挂自定义端点。

阶段1：/health 探活。
阶段2：/internal/* 端点（Agent CRUD / publish / rollback）——只面向
       parlant-agent-server（BFF），阶段3 起由 server 代理前端调用。
"""

from fastapi import FastAPI

from app.config import get_settings
from app.routers.internal_api import configure_internal_api
from app.utils.observability import instrument_fastapi


async def configure_api(app: FastAPI) -> None:
    settings = get_settings()
    # 必须在加路由之前调用：instrument 已注册的路由；
    # 此刻 Parlant 的全局 TracerProvider 已就绪（setup_container 先于 configure_api）。
    instrument_fastapi(app)

    # 阶段2：/internal/* 端点（Agent CRUD / publish / rollback）
    await configure_internal_api(app)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "parlant-agent-runtime",
            "mongo": settings.mongo_uri.split("@")[-1],  # 不回显账号密码
            "qdrant": settings.qdrant_url,
        }
