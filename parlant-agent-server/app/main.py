"""parlant-agent-server（BFF / 元数据服务）应用装配。

架构定位（2026-09-22 起）：
- 前端（parlant-agent-web）唯一后端入口：Agent 定义 CRUD/版本/发布编排 +
  会话代理（REST + SSE 透传）。
- 定义层（MongoDB agent_definitions）由本服务**独占写**；发布时把定义推送给
  parlant-agent-runtime（POST /internal/agents/{id}/load）热加载。
- 本服务不承载 Parlant 引擎；引擎在 parlant-agent-runtime（p.Server()）。

lifespan：启动时建连接层（MongoConnection + MySqlConnection）→ 仓储层
（AgentDefinitionRepository + UserSessionRepository，建索引/表）→ RuntimeClient，
挂到 app.state；关闭时释放连接。路由经 routers/__init__ 统一注册。

运行：
    uvicorn app.main:app --host 0.0.0.0 --port 8081
    或：python -m app.main
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.boundary import RuntimeClient
from app.config import get_settings
from app.databases import MongoConnection, MySqlConnection
from app.repository import (
    AgentDefinitionRepository,
    SessionMessageRepository,
    UserSessionRepository,
)
from app.routers import (
    agents_router,
    customers_router,
    health_router,
    internal_router,
    sessions_router,
)
from app.services import AgentDefinitionService, SessionService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    # 连接层：只建连接/句柄
    mongo = MongoConnection(settings.mongo_uri)
    mysql = MySqlConnection(settings.mysql_uri)

    # 仓储层：注入连接句柄，建索引/表
    agent_repo = AgentDefinitionRepository(mongo)
    await agent_repo.ensure_indexes()
    session_repo = UserSessionRepository(mysql)
    await session_repo.ensure_schema()
    message_repo = SessionMessageRepository(mysql)
    await message_repo.ensure_schema()

    # 领域服务
    runtime_client = RuntimeClient(
        settings.runtime_base_url, timeout=settings.runtime_timeout
    )
    agent_service = AgentDefinitionService(agent_repo, runtime_client)
    session_service = SessionService(
        runtime_client, session_repo, message_repo=message_repo, agent_repo=agent_repo
    )

    app.state.mongo = mongo
    app.state.mysql = mysql
    app.state.agent_repository = agent_repo
    app.state.session_repository = session_repo
    app.state.message_repository = message_repo
    app.state.runtime_client = runtime_client
    app.state.agent_service = agent_service
    app.state.session_service = session_service
    yield
    await mongo.close()
    await mysql.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.service_name, version="0.1.0", lifespan=lifespan)

    # 阶段3 前后端分离联调放开 CORS（生产按 cors_allow_origins 收紧）
    origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(agents_router)
    app.include_router(sessions_router)
    app.include_router(customers_router)
    app.include_router(internal_router)
    return app


app = create_app()


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    asyncio.run(main())