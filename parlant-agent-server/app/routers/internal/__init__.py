"""internal 子包：面向 parlant-agent-runtime 的内部端点（`/api/internal/*`，不面向前端）。

对外路由在 `app/routers/` 顶层（agents / sessions / traces / health）。
"""

from app.routers.internal.agents import router as internal_agents_router

__all__ = ["internal_agents_router"]
