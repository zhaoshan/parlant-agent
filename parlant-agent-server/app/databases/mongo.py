"""MongoDB 连接管理（motor）。

只负责连接生命周期与句柄产出；业务集合读写见 `app/repository/`。
"""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase


class MongoConnection:
    def __init__(self, mongo_uri: str, db_name: str = "parlant") -> None:
        self._client = AsyncIOMotorClient(mongo_uri)
        # 从 URI 路径取库名，缺省 parlant
        path_db = mongo_uri.rsplit("/", 1)[-1].split("?")[0] or db_name
        self.database: AsyncIOMotorDatabase = self._client[path_db]

    async def ping(self) -> bool:
        try:
            await self._client.admin.command("ping")
            return True
        except Exception:  # noqa: BLE001 - 探活失败即不可用
            return False

    async def close(self) -> None:
        self._client.close()