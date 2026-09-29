"""路由包：runtime FastAPI app 装配入口（/health + /internal/* 引擎控制面）。"""

from app.routers.app_setup import configure_api

__all__ = ["configure_api"]
