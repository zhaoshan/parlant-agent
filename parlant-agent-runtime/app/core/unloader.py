"""级联卸载（AgentUnloader）：删 agent 及其全部子实体。

旅程相关指南有两类**不在** agent:<id> 标签下，必须经 RelationshipStore 反查：
① 触发器指南（journey.triggers 引用的 GuidelineId）；② 旅程级指南（tags=[]，
靠 RelationshipStore 的 DEPENDENCY 关系关联）。其余实体按 agent 标签 list+delete。

从 app/services/agent_loader.py 拆分（2026-11），仅搬迁、逻辑零改动。
"""

from __future__ import annotations

import parlant.sdk as p
from parlant.sdk import _Tag
from parlant.core.agents import AgentStore
from parlant.core.canned_responses import CannedResponseStore
from parlant.core.context_variables import ContextVariableStore
from parlant.core.glossary import GlossaryStore
from parlant.core.guidelines import GuidelineStore
from parlant.core.journeys import JourneyStore
from parlant.core.relationships import RelationshipStore

from app.services import eval_status


class AgentUnloader:
    def __init__(self, server: p.Server) -> None:
        self._server = server

    async def unload(self, agent_id: str) -> bool:
        """卸载 agent 及其子实体；不存在返回 False。"""
        if not await self._server.find_agent(id=agent_id):
            return False
        await self.delete_entities(agent_id)
        eval_status.drop_instance(agent_id)
        return True

    async def delete_entities(self, agent_id: str) -> None:
        """删 agent 及所有子实体（指南/旅程/术语/变量/话术）。"""
        container = self._server.container
        tag_id = _Tag.for_agent_id(p.AgentId(agent_id)).id

        # 先清旅程相关指南（两类，均不在 agent:<agent_id> 标签下）：
        # ① 触发器指南：journey.triggers 里引用的 GuidelineId（打 journey:<journey_id> 标签）；
        # ② 旅程级指南：Journey.create_guideline 持久化为 tags=[]，与旅程的关联靠
        #    RelationshipStore 里 source=guideline、target=TAG_ALL(journey:<journey_id>)
        #    的 DEPENDENCY 关系（sdk.py _create_guideline: relationship_target_tag_id）。
        #    按 tag list 永远查不到，必须经 RelationshipStore 反查。
        guideline_store = container[GuidelineStore]
        relationship_store = container[RelationshipStore]
        try:
            journeys = await container[JourneyStore].list_journeys(tags=[tag_id])
        except Exception:  # noqa: BLE001 - list 失败不阻断后续清理
            journeys = []
        for journey in journeys:
            journey_tag = _Tag.for_journey_id(journey.id).id
            journey_guideline_ids = set(journey.triggers)
            try:
                rels = await relationship_store.list_relationships(target_id=journey_tag)
                for rel in rels:
                    if rel.source.kind.name == "GUIDELINE":
                        journey_guideline_ids.add(rel.source.id)
                    try:
                        await relationship_store.delete_relationship(rel.id)
                    except Exception:  # noqa: BLE001 - 尽力删除
                        pass
            except Exception:  # noqa: BLE001
                pass
            for gid in journey_guideline_ids:
                try:
                    await guideline_store.delete_guideline(gid)
                except Exception:  # noqa: BLE001 - 尽力删除
                    pass

        # 清理本 agent 的定义层 relationships（加载时带 group_id=agent.id 标记；journey
        # 引擎内部 REEVALUATION 等关系无 group_id，不受影响）
        try:
            for rel in await relationship_store.list_relationships():
                if rel.group_id == agent_id:
                    await relationship_store.delete_relationship(rel.id)
        except Exception:  # noqa: BLE001 - 尽力清理
            pass

        # 再按 agent 标签清其余实体（含 agent 级指南）；各自 list_* 都支持 tags 过滤
        stores = [
            (GuidelineStore, "list_guidelines", "delete_guideline"),
            (JourneyStore, "list_journeys", "delete_journey"),
            (GlossaryStore, "list_terms", "delete_term"),
            (ContextVariableStore, "list_variables", "delete_variable"),
            (CannedResponseStore, "list_canned_responses", "delete_canned_response"),
        ]
        for store_cls, list_method, del_method in stores:
            store = container[store_cls]
            try:
                items = await getattr(store, list_method)(tags=[tag_id])
            except Exception:  # noqa: BLE001 - 该 store 不支持 tags 过滤则跳过
                continue
            for item in items:
                try:
                    await getattr(store, del_method)(item.id)
                except Exception:  # noqa: BLE001 - 尽力删除，最后统一删 agent
                    pass
        await container[AgentStore].delete_agent(p.AgentId(agent_id))
