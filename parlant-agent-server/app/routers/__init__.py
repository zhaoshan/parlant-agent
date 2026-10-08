"""路由包：对外 REST（/api/agents/*、/api/sessions/*、/api/customers/*、/api/traces/*、/health）
+ 面向 runtime 的内部端点（/api/internal/*，见 ``internal`` 子包）。

- agents：Agent 定义 CRUD/版本/发布编排（server 独占写）。
- sessions：会话代理 + SSE 透传 + 客户代理（任务 3.3）。
- traces：链路历史数据代理（langfuse 取数，web 链路历史 tab）。
- health：探活。
- internal：面向 parlant-agent-runtime 的内部端点（当前 published-agents 拉取，可扩展）。
"""

from app.routers.agents import router as agents_router
from app.routers.health import router as health_router
from app.routers.internal import internal_agents_router
from app.routers.sessions import customers_router, sessions_router
from app.routers.settings import router as settings_router
from app.routers.traces import traces_router

__all__ = [
    "health_router",
    "agents_router",
    "sessions_router",
    "customers_router",
    "traces_router",
    "settings_router",
    "internal_agents_router",
]
