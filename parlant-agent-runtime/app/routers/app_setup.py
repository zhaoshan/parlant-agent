"""runtime FastAPI app 装配：p.Server(configure_api=...) 的扩展入口。

在 Parlant 的 FastAPI app 上挂自定义端点：
- `/health` 探活；
- `/internal/*` 引擎控制面（见 ``engine_control``，只面向 parlant-agent-server）。
"""

from fastapi import FastAPI

from app.config import get_settings
from app.routers.engine_control import configure_internal_api
from app.extensions.observability.langfuse_otel import instrument_fastapi


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
