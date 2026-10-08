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

# 逻辑删除墓碑：所有对外读过滤器。deleted_at 为 null 或缺失都视为未删除（Mongo 语义）。
_NOT_DELETED = {"deleted_at": None}


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
        """保存（覆盖同版本）一个定义版本；同时清除逻辑删除墓碑（覆盖即视为恢复/重建）。"""
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
                "$unset": {"deleted_at": ""},  # 覆盖保存 = 重建/恢复，去掉墓碑
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

    async def delete_agent_all(self, agent_id: str) -> int:
        """物理彻底删除一个 agent 的全部版本——不可恢复（逻辑删除见 ``soft_delete_agent``）。"""
        res = await self._col.delete_many({"agent_id": agent_id})
        return res.deleted_count

    async def soft_delete_agent(self, agent_id: str) -> int:
        """逻辑删除一个 agent：给全部版本文档打 `deleted_at` 墓碑，定义保留在库、可恢复。"""
        res = await self._col.update_many(
            {"agent_id": agent_id},
            {"$set": {"deleted_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}},
        )
        return res.matched_count

    async def exists(self, agent_id: str) -> bool:
        """该 agent_id 是否已有"未删除"的任意版本（create 查重用；逻辑删除后不算存在，可重建）。"""
        query = {"agent_id": agent_id, **_NOT_DELETED}
        return await self._col.count_documents(query, limit=1) > 0

    # ------------------------------------------------------------ 读
    async def get(self, agent_id: str, version: str) -> dict[str, Any] | None:
        return await self._col.find_one({"agent_id": agent_id, "version": version, **_NOT_DELETED})

    async def get_published(self, agent_id: str) -> dict[str, Any] | None:
        return await self._col.find_one(
            {"agent_id": agent_id, "status": STATUS_PUBLISHED, **_NOT_DELETED}, sort=[("updated_at", -1)]
        )

    async def list_published(self) -> list[dict[str, Any]]:
        """全部 published 定义（供 runtime 启动拉取）。"""
        cursor = self._col.find({"status": STATUS_PUBLISHED, **_NOT_DELETED}).sort("updated_at", -1)
        return await cursor.to_list(length=500)

    async def list_others_latest(self, exclude_agent_id: str) -> list[dict[str, Any]]:
        """其它每个 agent 的最新定义（跨 Agent 定义层 id 冲突预检用）。

        取每个 agent 最新更新的一份定义（不限状态），返回 `[{"agent_id", "definition"}]`。
        """
        pipeline = [
            {"$match": {"agent_id": {"$ne": exclude_agent_id}, **_NOT_DELETED}},
            {"$sort": {"updated_at": -1}},
            {"$group": {"_id": "$agent_id", "latest": {"$first": "$$ROOT"}}},
        ]
        return [
            {"agent_id": g["_id"], "definition": g["latest"].get("definition", {})}
            async for g in self._col.aggregate(pipeline)
        ]

    async def list_versions(self, agent_id: str) -> list[dict[str, Any]]:
        cursor = self._col.find({"agent_id": agent_id, **_NOT_DELETED}).sort("updated_at", -1)
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
            {"$match": _NOT_DELETED},
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
                    "description": latest.get("definition", {}).get("agent", {}).get("description"),
                    "published_version": published["version"] if published else None,
                    "latest_version": latest["version"],
                    "latest_status": latest["status"],
                    "updated_at": latest.get("updated_at"),
                    # 组件统计：对「最新定义」（草稿优先，无草稿即已发布）计数，与首页卡片/详情展示一致
                    "summary": self._summary_counts(latest.get("definition") or {}),
                }
            )
        return out

    @staticmethod
    def _summary_counts(d: dict[str, Any]) -> dict[str, int]:
        """组件计数（与 services.agents 详情 summary 同语义；不含 relationship/observation/retriever）。"""
        journeys = (d.get("journeys") or {}).get("journeys") or []
        return {
            "guidelines": len((d.get("guidelines") or {}).get("guidelines") or []),
            "journeys": len(journeys),
            "states": sum(len(j.get("states") or []) for j in journeys),
            "variables": len((d.get("variables") or {}).get("variables") or []),
            "glossary": len((d.get("glossary") or {}).get("glossary") or []),
            "canned_responses": len((d.get("canned_responses") or {}).get("responses") or []),
            "tools": len((d.get("tools") or {}).get("tools") or []),
        }