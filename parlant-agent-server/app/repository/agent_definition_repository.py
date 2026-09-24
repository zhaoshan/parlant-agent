"""AgentDefinitionRepository——Agent 定义层仓储（MongoDB `agent_definitions`）。

由 parlant-agent-server **独占写**（定义层归属），runtime 侧降级为被动接收推送 + 启动拉取。

collection 文档结构：
    { agent_id, version, status, definition, created_at, updated_at, created_by }
- status: draft | published | archived
- 多版本并存；每个 agent_id 至多一个 published（发布时把旧 published 置 archived）。
- definition 存完整定义 JSON（与 agent-definition.json 同构）。

连接句柄由 `databases.MongoConnection` 注入；索引/操作均属本仓储职责。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from app.databases import MongoConnection

STATUS_DRAFT = "draft"
STATUS_PUBLISHED = "published"
STATUS_ARCHIVED = "archived"

_COLLECTION = "agent_definitions"


class AgentDefinitionRepository:
    def __init__(self, mongo: MongoConnection) -> None:
        self._col: AsyncIOMotorCollection = mongo.database[_COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._col.create_index([("agent_id", 1), ("version", 1)], unique=True)
        await self._col.create_index([("agent_id", 1), ("status", 1)])

    # ------------------------------------------------------------ 写
    async def save(
        self,
        agent_id: str,
        definition: dict[str, Any],
        version: str,
        created_by: str = "system",
        status: str = STATUS_DRAFT,
    ) -> dict[str, Any]:
        """保存（覆盖同版本）一个定义版本。"""
        now = datetime.now(timezone.utc)
        await self._col.update_one(
            {"agent_id": agent_id, "version": version},
            {
                "$set": {
                    "status": status,
                    "definition": definition,
                    "created_by": created_by,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        return {"agent_id": agent_id, "version": version, "status": status}

    async def set_status(self, agent_id: str, version: str, status: str) -> bool:
        """切换版本状态；发布时把同 agent 其它 published 置 archived。"""
        res = await self._col.update_one(
            {"agent_id": agent_id, "version": version},
            {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}},
        )
        if status == STATUS_PUBLISHED:
            await self._col.update_many(
                {"agent_id": agent_id, "version": {"$ne": version}, "status": STATUS_PUBLISHED},
                {"$set": {"status": STATUS_ARCHIVED, "updated_at": datetime.now(timezone.utc)}},
            )
        return res.matched_count > 0

    async def delete_version(self, agent_id: str, version: str) -> bool:
        """物理删除单个版本文档（清理多余 draft / 历史版本）。"""
        res = await self._col.delete_one({"agent_id": agent_id, "version": version})
        return res.deleted_count > 0

    async def delete_versions_by_status(self, agent_id: str, status: str) -> int:
        """按状态批量删除（用于"每 agent 只有一个 draft"的归一化）。"""
        res = await self._col.delete_many({"agent_id": agent_id, "status": status})
        return res.deleted_count

    # ------------------------------------------------------------ 读
    async def get(self, agent_id: str, version: str) -> dict[str, Any] | None:
        return await self._col.find_one({"agent_id": agent_id, "version": version})

    async def get_published(self, agent_id: str) -> dict[str, Any] | None:
        return await self._col.find_one(
            {"agent_id": agent_id, "status": STATUS_PUBLISHED}, sort=[("updated_at", -1)]
        )

    async def list_published(self) -> list[dict[str, Any]]:
        """全部 published 定义（供 runtime 启动拉取）。"""
        cursor = self._col.find({"status": STATUS_PUBLISHED}).sort("updated_at", -1)
        return await cursor.to_list(length=500)

    async def list_versions(self, agent_id: str) -> list[dict[str, Any]]:
        cursor = self._col.find({"agent_id": agent_id}).sort("updated_at", -1)
        return [
            {
                "version": d["version"],
                "status": d["status"],
                "created_by": d.get("created_by"),
                "created_at": d.get("created_at"),
                "updated_at": d.get("updated_at"),
            }
            for d in await cursor.to_list(length=100)
        ]

    async def list_agents(self) -> list[dict[str, Any]]:
        """列出全部 agent 及其当前 published/draft 版本概要。

        `name` 取最新版本定义里的 `agent.name`（侧栏下拉等 UI 展示用；旧定义
        可能缺失，回退 agent_id）。
        """
        pipeline = [
            {"$sort": {"updated_at": -1}},
            {"$group": {"_id": "$agent_id", "docs": {"$push": "$$ROOT"}}},
        ]
        out = []
        async for grp in self._col.aggregate(pipeline):
            docs = grp["docs"]
            published = next((d for d in docs if d["status"] == STATUS_PUBLISHED), None)
            latest = docs[0]
            out.append(
                {
                    "agent_id": grp["_id"],
                    "name": (
                        latest.get("definition", {}).get("agent", {}).get("name")
                        or grp["_id"]
                    ),
                    "published_version": published["version"] if published else None,
                    "latest_version": latest["version"],
                    "latest_status": latest["status"],
                    "updated_at": latest.get("updated_at"),
                }
            )
        return out