"""路由包：对外 REST（/api/agents/*、/api/sessions/*、/api/customers/*、/api/traces/*）+ 内部（/api/internal/*）+ /health。

- api_agents：Agent 定义 CRUD/版本/发布编排（server 独占写）。
- api_sessions：会话代理 + SSE 透传 + 客户代理（任务 3.3）。
- api_traces：链路历史数据代理（langfuse 取数，web 链路历史 tab）。
- api_internal：面向 runtime 的内部端点（published-agents 拉取）。
"""

from app.routers.api_agents import router as agents_router
from app.routers.api_internal import router as internal_router
from app.routers.api_sessions import customers_router, sessions_router
from app.routers.api_traces import traces_router
from app.routers.health import router as health_router

__all__ = [
    "health_router",
    "agents_router",
    "sessions_router",
    "customers_router",
    "traces_router",
    "internal_router",
]
