"""路由包：configure_api 扩展挂载的端点（/health + /internal/*）。"""

from app.routers.api_extensions import configure_api

__all__ = ["configure_api"]
