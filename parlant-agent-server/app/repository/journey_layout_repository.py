"""JourneyLayoutRepository——旅程流程图 UI 布局（MongoDB `journey_layouts`）。

存**纯 UI 的连线挂载点（anchor）配置**：transition 的源/目标端挂在节点方块的哪条
边中点（top/right/bottom/left）。与 Agent 定义层（`agent_definitions`）**完全解耦**：
不写定义文档、不进版本 diff、无需保存草稿/发布即生效；草稿与线上共享同一份布局
（按 agent_id + journey_id 存，不区分版本）。

collection 文档结构：
    { agent_id, journey_id, edges: { "<from>|<transition_key>": {from_anchor?, to_anchor?} },
      nodes: { "<state_id>": {x, y} },  updated_at }
- 键由前端生成（transition_id → condition → 序号兜底），server 透明存储、不解释。
- 引擎不消费本集合；runtime 零接触。

连接句柄由 `databases.MongoConnection` 注入；索引/操作均属本仓储职责。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from app.databases import MongoConnection

_COLLECTION = "journey_layouts"


class JourneyLayoutRepository:
    def __init__(self, mongo: MongoConnection) -> None:
        self._col: AsyncIOMotorCollection = mongo.database[_COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._col.create_index([("agent_id", 1), ("journey_id", 1)], unique=True)

    # ------------------------------------------------------------ 读写
    async def get(self, agent_id: str, journey_id: str) -> dict[str, Any] | None:
        doc = await self._col.find_one({"agent_id": agent_id, "journey_id": journey_id})
        if doc:
            doc.pop("_id", None)
        return doc

    async def save(
        self, agent_id: str, journey_id: str, edges: dict[str, Any], nodes: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """整体覆盖该旅程的布局（edges/nodes 全量替换；upsert，无草稿态要求）。"""
        now = datetime.now(timezone.utc)
        await self._col.update_one(
            {"agent_id": agent_id, "journey_id": journey_id},
            {
                "$set": {"edges": edges, "nodes": nodes or {}, "updated_at": now},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        return {
            "agent_id": agent_id,
            "journey_id": journey_id,
            "edges": edges,
            "nodes": nodes or {},
            "updated_at": now,
        }
