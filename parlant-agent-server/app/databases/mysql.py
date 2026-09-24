"""MySQL 连接管理（SQLAlchemy async + aiomysql）。

只负责连接/引擎生命周期；表结构与业务读写见 `app/repository/`（如 user_session_repository）。
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


class MySqlConnection:
    def __init__(self, mysql_uri: str) -> None:
        # 期望形如 mysql+aiomysql://user:pass@host:port/db
        self.engine: AsyncEngine = create_async_engine(mysql_uri, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def ping(self) -> bool:
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001 - 探活失败即不可用
            return False

    async def close(self) -> None:
        await self.engine.dispose()