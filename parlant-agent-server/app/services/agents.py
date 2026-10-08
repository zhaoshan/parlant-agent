"""Agent 元数据服务：定义 CRUD / 版本 / 发布编排（server 独占写定义层）。

- 校验：当前只做**轻量结构校验**（有 agent.id/version）；深度校验由 runtime 在
  load 时兜底（422 透传）。`agent-definition.json` 的 pydantic 模型抽共享包
  （server/runtime/web 三方共用）留待阶段4 前落地（见 plan 阶段3 任务 3.2）。
- 发布链路：取目标版本定义 -> RuntimeClient.load_agent 推送 runtime 热加载
  -> 成功才 set_status(published)（旧 published 自动置 archived）；
  runtime 加载失败抛 PublishError（不改状态）。
"""

from __future__ import annotations

from typing import Any

import httpx

from app.boundary import RuntimeClient
from app.repository import (
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    AgentDefinitionRepository,
)

DEFAULT_VERSION = "1.0.0"


class PublishError(Exception):
    """发布/回滚失败（runtime 加载失败等），携带 HTTP 状态与详情。"""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class AgentDefinitionService:
    def __init__(self, agent_repo: AgentDefinitionRepository, runtime_client: RuntimeClient) -> None:
        self._repo = agent_repo
        self._runtime = runtime_client

    # ------------------------------------------------------------ 校验（轻量）
    @staticmethod
    def _extract_identity(data: dict[str, Any]) -> tuple[str, str]:
        """轻量结构校验：要求顶层有 agent.id（version 缺省 1.0.0）。"""
        agent = data.get("agent")
        if not isinstance(agent, dict) or not agent.get("id"):
            raise ValueError("定义缺少 agent.id")
        return str(agent["id"]), str(agent.get("version") or DEFAULT_VERSION)

    # 定义层提供、进引擎**全局**存储的实体 id（多 Agent 必须全局唯一；@draft 实例虽由
    # loader 加后缀隔离，published 无后缀直接进全局存储）。variable/glossary/canned
    # 的 id 由 SDK 随机生成、tool 按名注册（同名视为复用），均不在此预检范围。
    _ID_KIND_LABELS: dict[str, str] = {
        "journey": "journey id (jny_*)",
        "state": "state id (sta_*)",
        "guideline": "guideline id (gdl_*)",
        "observation": "observation id (obs_*)",
    }

    @classmethod
    def _extract_definition_ids(cls, data: dict[str, Any]) -> dict[str, set[str]]:
        """提取定义层提供的全局存储 id：journey / state / guideline / observation。"""
        def _ids(section: str, key: str) -> set[str]:
            items = (data.get(section) or {}).get(key) or []
            return {str(i["id"]) for i in items if isinstance(i, dict) and i.get("id")}

        def _ids_from(items: Any) -> set[str]:
            return {str(i["id"]) for i in items or [] if isinstance(i, dict) and i.get("id")}

        journeys = _ids("journeys", "journeys")
        states: set[str] = set()
        for j in (data.get("journeys") or {}).get("journeys") or []:
            states |= _ids_from(j.get("states"))
        return {
            "journey": journeys,
            "state": states,
            "guideline": _ids("guidelines", "guidelines"),
            "observation": _ids("observations", "observations"),
        }

    async def _check_cross_agent_id_conflicts(self, agent_id: str, data: dict[str, Any]) -> None:
        """跨 Agent 定义层 id 冲突预检（导入即报错）。

        journey/state/guideline/observation 进引擎全局存储，多 Agent 必须全局唯一；
        加载器在发布/热加载时也会兜底拦截（撞号报错），这里把报错提前到导入/save。
        """
        mine = self._extract_definition_ids(data)
        others = await self._repo.list_others_latest(agent_id)
        by_kind: dict[str, list[tuple[str, str]]] = {}
        for other in others:
            theirs = self._extract_definition_ids(other["definition"])
            for kind, ids in mine.items():
                for x in sorted(ids):
                    if x in theirs[kind]:
                        by_kind.setdefault(kind, []).append((x, other["agent_id"]))
        if not by_kind:
            return
        parts = [
            f"{self._ID_KIND_LABELS[kind]}[{', '.join(x for x, _ in v)}] 已被 Agent '{v[0][1]}' 使用"
            for kind, v in by_kind.items()
        ]
        raise ValueError(
            "定义层 id 与现有 Agent 冲突（进引擎全局存储，须全局唯一）："
            + "；".join(parts)
            + "。请改用全局唯一 id（建议带 agent 专属前缀）后重新保存。"
        )

    # ------------------------------------------------------------ 写
    DRAFT_VERSION = "draft"  # 草稿固定槽位（每 agent 一个）

    async def save(
        self,
        data: dict[str, Any],
        created_by: str = "api",
        strict: bool = False,
    ) -> dict[str, Any]:
        """保存为草稿：固定落到 `draft` 槽位，并清理其它 draft —— 保证每 agent 只有一个草稿。

        `strict=True`（创建 Agent 专用）：agent_id 已存在则拒绝（本端点同时被「构建保存草稿」
        复用，故查重只在创建路径开启，避免误伤对既有 agent 的草稿更新）。
        """
        agent_id, _ = self._extract_identity(data)
        if strict and await self._repo.exists(agent_id):
            raise ValueError(f"agent_id '{agent_id}' 已存在，不能重复创建")
        await self._check_cross_agent_id_conflicts(agent_id, data)
        # 归一化：删掉所有其它 draft 版本，只留当前槽
        await self._repo.delete_versions_by_status(agent_id, STATUS_DRAFT)
        return await self._repo.save(agent_id, data, self.DRAFT_VERSION, created_by=created_by,
                                     status=STATUS_DRAFT)

    # ------------------------------------------------------------ 读
    async def _loaded_ids(self) -> set[str]:
        """runtime 已加载的 agent id 集合；runtime 不可达时降级为空集（不阻断列表查询）。"""
        try:
            return {a["agent_id"] for a in (await self._runtime.list_loaded()).get("agents", [])}
        except Exception:  # noqa: BLE001 - httpx 连接错/5xx（runtime 未起/半死）均降级
            return set()

    async def list_agents(self) -> list[dict[str, Any]]:
        infos = await self._repo.list_agents()
        loaded = await self._loaded_ids()
        return [{**info, "loaded": info["agent_id"] in loaded} for info in infos]

    async def get(self, agent_id: str, version: str | None = None) -> dict[str, Any] | None:
        """取定义详情；`version` 指定时取该版本（版本对比/diff 用），缺省取 published（无则最新）。"""
        doc = (
            await self._repo.get(agent_id, version)
            if version
            else await self._repo.get_published(agent_id) or await self._latest(agent_id)
        )
        if not doc:
            return None
        loaded = await self._loaded_ids()
        d = doc["definition"]
        return {
            "agent_id": agent_id,
            "version": doc["version"],
            "status": doc["status"],
            "loaded": agent_id in loaded,
            "summary": {
                "guidelines": len(d.get("guidelines", {}).get("guidelines", [])),
                "journeys": len(d.get("journeys", {}).get("journeys", [])),
                "states": sum(
                    len(j.get("states", [])) for j in d.get("journeys", {}).get("journeys", [])
                ),
                "variables": len(d.get("variables", {}).get("variables", [])),
                "glossary": len(d.get("glossary", {}).get("glossary", [])),
                "canned_responses": len(d.get("canned_responses", {}).get("responses", [])),
                "tools": len(d.get("tools", {}).get("tools", [])),
            },
            "definition": d,
        }

    async def list_versions(self, agent_id: str) -> list[dict[str, Any]]:
        return await self._repo.list_versions(agent_id)

    # ------------------------------------------------------------ 发布 / 回滚 / 停用
    async def publish(self, agent_id: str, version: str | None = None) -> dict[str, Any]:
        """发布当前草稿：目标版本号由 server 决定（缺省=从已发布版本 patch+1），校验唯一。

        流程：取 draft 槽草稿 → 定目标版本 → 推 runtime 热加载（published 用裸 id）→
        落库 target=published（旧 published 置 archived）→ 清空草稿槽。
        """
        doc = await self._repo.get(agent_id, self.DRAFT_VERSION)
        if not doc:
            doc = await self._latest_draft(agent_id)  # 兼容：迁移前残留在其它版本号的草稿
        if not doc:
            raise PublishError(404, f"agent '{agent_id}' 没有草稿可发布")

        if version:
            target = version
            if await self._repo.get(agent_id, target):
                raise PublishError(409, f"版本 '{target}' 已存在")
        else:
            published = await self._repo.get_published(agent_id)
            target = self._next_version((published or {}).get("version"))

        # 构造发布定义（agent.version = 目标正式版本）
        definition = dict(doc["definition"])
        definition.setdefault("agent", {})["version"] = target

        # 推送 runtime 热加载（成功才落 published）
        try:
            resp = await self._runtime.load_agent(agent_id, definition)
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:400] if exc.response is not None else str(exc)
            raise PublishError(exc.response.status_code if exc.response else 500, detail) from exc
        except httpx.HTTPError as exc:
            raise PublishError(500, f"runtime 不可达：{exc}") from exc

        # 落库：target 置 published（set_status 会把其它 published 置 archived）
        await self._repo.save(agent_id, definition, target, created_by="api", status=STATUS_PUBLISHED)
        await self._repo.set_status(agent_id, target, STATUS_PUBLISHED)
        # 发布后清空草稿槽
        await self._repo.delete_version(agent_id, self.DRAFT_VERSION)
        return {"agent_id": agent_id, "version": target, "loaded_agent": resp["loaded_agent"]}

    async def rollback(self, agent_id: str, version: str) -> dict[str, Any]:
        """回滚到历史版本：推 runtime + 置 published；回滚后清空草稿槽（避免草稿残留）。"""
        doc = await self._repo.get(agent_id, version)
        if not doc:
            raise PublishError(404, f"agent '{agent_id}' 版本 '{version}' 不存在")
        result = await self._push_and_mark(agent_id, doc)
        await self._repo.delete_version(agent_id, self.DRAFT_VERSION)
        return result

    async def unload(self, agent_id: str) -> bool:
        resp = await self._runtime.unload_agent(agent_id)
        return bool(resp.get("unloaded"))

    async def delete_version(self, agent_id: str, version: str) -> dict[str, Any]:
        """物理删除单个版本文档（清理多余 draft / 历史版本）；不允许删当前 published。"""
        doc = await self._repo.get(agent_id, version)
        if not doc:
            return {"deleted": False, "agent_id": agent_id, "version": version}
        if doc["status"] == STATUS_PUBLISHED:
            return {
                "deleted": False,
                "agent_id": agent_id,
                "version": version,
                "error": "不能删除当前已发布版本，请先发布其它版本或归档",
            }
        ok = await self._repo.delete_version(agent_id, version)
        return {"deleted": ok, "agent_id": agent_id, "version": version}

    async def delete_agent(self, agent_id: str) -> dict[str, Any]:
        """逻辑删除（设置页「删除当前 Agent」）：卸载运行时实体 + 给定义层打 `deleted_at` 墓碑。

        定义**保留在 Mongo、可恢复**，只是从列表/查询中隐藏；服务端 `strict` 创建视其为不存在。
        """
        try:
            await self._runtime.unload_agent(agent_id)
        except httpx.HTTPStatusError as exc:
            if exc.response is None or exc.response.status_code != 404:
                raise
        matched = await self._repo.soft_delete_agent(agent_id)
        return {"agent_id": agent_id, "deleted": True, "soft": True, "versions_marked": matched}

    # ------------------------------------------------------------ 内部
    async def _latest_draft(self, agent_id: str) -> dict[str, Any] | None:
        """找任意 draft 状态的版本（兼容迁移前残留在其它版本号的草稿）。"""
        for v in await self._repo.list_versions(agent_id):
            if v.get("status") == STATUS_DRAFT:
                return await self._repo.get(agent_id, v["version"])
        return None

    @staticmethod
    def _next_version(current: str | None) -> str:
        """从当前已发布版本递增 patch（major.minor.patch）；无则 1.0.0。"""
        if not current:
            return "1.0.0"
        try:
            parts = [int(p) for p in str(current).split(".")[:3]]
            parts += [0] * (3 - len(parts))
        except ValueError:
            return "1.0.0"
        parts[2] += 1
        return ".".join(str(n) for n in parts)

    async def _push_and_mark(self, agent_id: str, doc: dict[str, Any]) -> dict[str, Any]:
        """推送给 runtime 热加载；成功后才置 published。"""
        try:
            resp = await self._runtime.load_agent(agent_id, doc["definition"])
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:400] if exc.response is not None else str(exc)
            raise PublishError(exc.response.status_code if exc.response else 500, detail) from exc
        except httpx.HTTPError as exc:
            raise PublishError(500, f"runtime 不可达：{exc}") from exc

        await self._repo.set_status(agent_id, doc["version"], STATUS_PUBLISHED)
        return {"agent_id": agent_id, "version": doc["version"], "loaded_agent": resp["loaded_agent"]}

    async def _resolve(self, agent_id: str, version: str | None) -> dict[str, Any] | None:
        if version:
            return await self._repo.get(agent_id, version)
        return await self._repo.get_published(agent_id) or await self._latest(agent_id)

    async def _latest(self, agent_id: str) -> dict[str, Any] | None:
        versions = await self._repo.list_versions(agent_id)
        if not versions:
            return None
        return await self._repo.get(agent_id, versions[0]["version"])