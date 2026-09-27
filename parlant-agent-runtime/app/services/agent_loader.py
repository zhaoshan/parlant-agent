"""阶段2.3：AgentLoader——把校验后的定义（app.models.definition.AgentDefinition）装配成 Parlant Agent。

这是阶段1.3「手动映射」的通用化：消费 pydantic 模型而非裸 dict，逻辑与
agent_bootstrap.py 一致（glossary/canned/variables/journeys/guidelines/tools）。
映射规则见 plan/阶段2 任务 2.3。

幂等语义：load() 先检查 agent_id 是否已存在——存在则先卸载（删 agent 及其
打 agent 标签的全部子实体）再重建，保证「重复加载同版本不重复建实体」、
「发布即生效」。
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import structlog
import parlant.sdk as p
from parlant.sdk import _Tag
from parlant.core.agents import AgentStore
from parlant.core.canned_responses import CannedResponseStore
from parlant.core.common import ItemNotFoundError
from parlant.core.context_variables import ContextVariableStore
from parlant.core.glossary import GlossaryStore
from parlant.core.guidelines import GuidelineStore
from parlant.core.journeys import JourneyStore
from parlant.core.relationships import RelationshipStore

from app.models.definition import AgentDefinition, GuidelineDef, JourneyDef
from app.services.builtin_tools import resolve_tool, set_runtime_services

logger = structlog.get_logger()

_COMPOSITION_MODES = {
    "fluid": p.CompositionMode.FLUID,
    "composited": p.CompositionMode.COMPOSITED,
    "canned_composited": p.CompositionMode.COMPOSITED,
    "strict": p.CompositionMode.STRICT,
}

_STATE_TYPES = {
    "chat": p.ChatJourneyState,
    "tool": p.ToolJourneyState,
    "fork": p.ForkJourneyState,
}


def _composition_mode(value: str | None) -> p.CompositionMode:
    return _COMPOSITION_MODES.get((value or "fluid").lower(), p.CompositionMode.FLUID)


def _instance_suffix(agent_id: str) -> str:
    """实例后缀：agent.id 中 '@' 起部分（如 '@draft'；主实例/未来 '@1.0.1'）。

    定义层实体 id（jny_*/sta_*）进引擎全局存储；同一定义多实例并存时靠后缀隔离，
    详见 _build_journey  docstring。追踪对账时剥掉后缀即定义层 id。
    """
    i = agent_id.find("@")
    return agent_id[i:] if i >= 0 else ""


def _split_synonyms(raw: Any) -> list[str]:
    """定义层 synonyms 常是逗号拼接的单串（如 ["a,b,c"]），拆成列表。"""
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [raw]
    out: list[str] = []
    for item in raw:
        out.extend(s.strip() for s in str(item).split(",") if s.strip())
    return out


class AgentLoader:
    """定义 -> Parlant 实体装配器（每个 p.Server() 一个实例即可）。"""

    def __init__(self, server: p.Server) -> None:
        self._server = server

    # ------------------------------------------------------------ 公开入口
    async def load(self, definition: AgentDefinition) -> p.Agent:
        agent_def = definition.agent
        # 内置工具（variable_update 写变量）需要容器访问
        set_runtime_services(self._server.container)

        # 幂等：已存在则先卸载（含子实体）再重建
        if await self._server.find_agent(id=agent_def.id):
            await self._delete_agent_entities(agent_def.id)

        agent = await self._server.create_agent(
            id=agent_def.id,
            name=agent_def.name,
            description=self._render_description(agent_def),
            composition_mode=_composition_mode(agent_def.composition_mode),
        )
        try:
            await self._build_glossary(agent, definition)
            canrep_map = await self._build_canned(agent, definition)
            await self._build_variables(agent, definition)
            journey_map = await self._build_journeys(agent, definition)
            await self._build_guidelines(agent, definition, canrep_map, journey_map)
            self._evaluate_journeys_now(list(journey_map.values()))
        except Exception:
            # 失败回滚：删干净，避免"建了一半"的 agent
            await self._delete_agent_entities(agent_def.id)
            raise
        return agent

    def _evaluate_journeys_now(self, journeys: list[p.Journey]) -> None:
        """热加载旅程**后台评估**并应用节点元数据（journey_node.reachable_follow_ups 等）。

        背景：SDK 的评估-应用（_process_evaluations → _apply_single_evaluation）只在
        __aexit__ 跑一遍，服务于"启动前已加载"的实体；热加载（publish/rollback 推送、
        @draft 草稿实例）的旅程等不到它 → 节点缺 reachable_follow_ups（分叉推进的
        条件表）→ 运行期 fork 选择条件为空 → LLM 任何回答都是 'invalid condition id'
        → 旅程无法推进。故此处逐旅程评估（内容哈希缓存，未变则秒回）并应用到节点；
        entity_cq 监听节点变更会把元数据投影到节点指南。

        注意**必须后台化**：旅程评估是逐节点多次 LLM 调用（实测可达数分钟），
        阻塞会拖住 load 响应/会话创建。评估完成前 fork 暂不可推进（entry/普通节点
        不受影响）；完成时打印日志。评估失败仅影响分叉推进，不阻断加载。
        """
        for journey in journeys:
            asyncio.create_task(self._evaluate_journey(journey))

    async def _evaluate_journey(self, journey: p.Journey) -> None:
        # —— 评估诊断日志（2026-09-27 排查草稿热加载评估）：哈希 + cache 命中预判 + 用时 + 分叉数 ——
        import time as _time

        t0 = _time.monotonic()
        _hash = ""
        cache_hit = None
        try:
            _hash = self._server._evaluator._hash_journey_evaluation_request(  # noqa: SLF001
                journey=journey
            )
            cached = await self._server._evaluator._journey_collection.find_one(  # noqa: SLF001
                {"id": {"$eq": _hash}}
            )
            cache_hit = cached is not None
        except Exception as exc:  # noqa: BLE001 - 诊断失败不影响评估
            logger.warning(f"[eval诊断] 哈希/命中预判失败 {journey.id}: {exc}")
        logger.info(
            f"[eval诊断] 旅程评估开始 id={journey.id} title={journey.title} "
            f"hash={(_hash or '?')[:8]} cache命中预判={cache_hit}"
        )
        try:
            result = await asyncio.wait_for(
                self._server._evaluator.evaluate_journey(journey),  # noqa: SLF001
                timeout=900,
            )
            await self._server._apply_single_evaluation(  # noqa: SLF001
                "journey", journey.id, result
            )
            fu_counts = {
                nid: len(np.get("journey_node", {}).get("reachable_follow_ups") or [])
                for nid, np in (result.node_properties or {}).items()
            }
            logger.info(
                f"[eval诊断] 旅程评估完成 id={journey.id} 用时={_time.monotonic() - t0:.1f}s "
                f"分叉数={fu_counts}"
            )
            print(f"✅ 旅程评估完成：{journey.title} ({journey.id})，分叉条件表已就绪", flush=True)
        except Exception as exc:  # noqa: BLE001 - 评估失败仅影响分叉推进
            logger.info(
                f"[eval诊断] 旅程评估失败 id={journey.id} 用时={_time.monotonic() - t0:.1f}s "
                f"错误={type(exc).__name__}: {exc}"
            )
            print(f"⚠️ 旅程评估失败（分叉推进可能退化）：{journey.id}: {exc}", flush=True)

    async def unload(self, agent_id: str) -> bool:
        """卸载 agent 及其子实体；不存在返回 False。"""
        if not await self._server.find_agent(id=agent_id):
            return False
        await self._delete_agent_entities(agent_id)
        return True

    # ------------------------------------------------------------ 卸载（级联）
    async def _delete_agent_entities(self, agent_id: str) -> None:
        """删 agent 及所有子实体（指南/旅程/术语/变量/话术）。"""
        container = self._server.container
        tag_id = _Tag.for_agent_id(p.AgentId(agent_id)).id

        # 先清旅程相关指南（两类，均不在 agent:<agent_id> 标签下）：
        # ① 触发器指南：journey.triggers 里引用的 GuidelineId（打 journey:<journey_id> 标签）；
        # ② 旅程级指南：Journey.create_guideline 持久化为 tags=[]，与旅程的关联靠
        #    RelationshipStore 里 source=guideline、target=TAG_ALL(journey:<journey_id>)
        #    的 DEPENDENCY 关系（sdk.py _create_guideline: relationship_target_tag_id）。
        #    按 tag list 永远查不到，必须经 RelationshipStore 反查。
        container = self._server.container
        tag_id = _Tag.for_agent_id(p.AgentId(agent_id)).id
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

    # ------------------------------------------------------------ 各组件映射
    @staticmethod
    def _render_description(agent_def: Any) -> str:
        description = agent_def.description
        boundary = agent_def.boundary
        if boundary.prohibited:
            description += "\n禁止事项：" + "；".join(boundary.prohibited)
        if agent_def.default_language:
            description += f"\n（默认语言：{agent_def.default_language}）"
        return description

    async def _build_glossary(self, agent: p.Agent, definition: AgentDefinition) -> None:
        for term in definition.glossary.glossary:
            await agent.create_term(
                name=term.name,
                description=term.description,
                synonyms=_split_synonyms(term.synonyms),
            )

    async def _build_canned(
        self, agent: p.Agent, definition: AgentDefinition
    ) -> dict[str, p.CannedResponseId]:
        id_map: dict[str, p.CannedResponseId] = {}
        for rsp in definition.canned_responses.responses:
            cid = await agent.create_canned_response(
                template=rsp.template,
                signals=rsp.signals,
            )
            id_map[rsp.id] = cid
        return id_map

    async def _build_variables(self, agent: p.Agent, definition: AgentDefinition) -> None:
        for var in definition.variables.variables:
            variable = await agent.create_variable(
                name=var.name,
                description=var.description or None,
                freshness_rules=var.freshness_rules or None,
            )
            await variable.set_value_for_agent(agent, var.default_value)

    async def _build_journeys(
        self, agent: p.Agent, definition: AgentDefinition
    ) -> dict[str, p.Journey]:
        journey_map: dict[str, p.Journey] = {}
        for j in definition.journeys.journeys:
            journey = await self._build_journey(agent, j)
            journey_map[j.id] = journey
        return journey_map

    async def _build_journey(
        self, agent: p.Agent, journey_def: JourneyDef
    ) -> p.Journey:
        """装配旅程状态图（先建全部状态保留定义层 id，再连 transitions，叶子接 END）。

        字段映射（阶段3.12 补全"可配置且生效"项）：
        - 旅程：title/description/triggers/composition_mode/**priority**
        - 状态：type/action(chat_state|tool_instruction)/tools(tool_state)/description/**composition_mode**/labels
        - 转移：condition/to/**canned_responses**（SDK create_transition 支持）

        实例隔离（2026-09-23）：定义层实体 id（jny_*/sta_*）进引擎**全局**存储。
        同一定义的多个实例（线上 + @draft 草稿/未来多版本）同时加载时，旅程 id 冲突
        会报错、状态 id 冲突会**静默覆盖**互相污染——故带实例后缀（如 jny_xxx@draft）。
        published 主实例无后缀，id 与定义层完全一致（追踪可直接对账）。
        """
        suffix = _instance_suffix(agent.id)
        journey = await agent.create_journey(
            title=journey_def.title or journey_def.description or "未命名旅程",
            description=journey_def.description,
            triggers=journey_def.triggers,
            composition_mode=_composition_mode(journey_def.composition_mode),
            priority=journey_def.priority or 0,
            id=p.JourneyId(f"{journey_def.id}{suffix}") if journey_def.id else None,
        )

        state_map: dict[str, p.JourneyState] = {}
        node_store = self._server.container[JourneyStore]
        for s in journey_def.states:
            stype = _STATE_TYPES.get(s.type, p.ChatJourneyState)
            tools = [resolve_tool(t) for t in s.tool_state]
            action = s.chat_state or s.tool_instruction or None
            state_id = p.JourneyStateId(f"{s.id}{suffix}")
            # [跨定义撞号防御·2026-09-27] load() 幂等：本实例旧实体已在开头删净，此时
            # 全局存储里仍存在的同 id 节点必属其它 Agent/定义。JourneyStore 对重复
            # 节点 id 是 insert_one 静默覆盖（曾因此互相污染），这里改为显式拒绝，
            # 把污染挡在发生前（前端 gid 已带定义内查重，此为最后防线）。
            try:
                await node_store.read_node(state_id)
            except ItemNotFoundError:
                pass
            else:
                raise RuntimeError(
                    f"旅程状态 id '{state_id}' 已存在于引擎全局存储（跨 Agent/定义撞号），"
                    "继续加载会静默覆盖其它定义的状态；请修改该状态 id 后重新保存/发布。"
                )
            state_map[s.id] = state = await journey._create_state(  # noqa: SLF001 见 agent_bootstrap
                stype,
                action=action,
                description=s.description or s.title or None,
                tools=tools,
                composition_mode=_composition_mode(s.composition_mode),
                id=state_id,
                labels=s.labels,
            )
            # [评估哈希修复·2026-09-27] SDK 的 _create_state 只写 store、不追加进
            # journey.states；而评估哈希 _hash_journey_evaluation_request 用的正是
            # journey.states/transitions → 不补齐则哈希只含根节点（常量），结构怎么改
            # 都命中首次评估、永不重评估（曾导致草稿加状态后仍用旧分叉表）。此处手动补齐。
            cast(list, journey.states).append(state)

        created_transitions: list = []
        if journey_def.entry_node and journey_def.entry_node in state_map:
            created_transitions.append(
                await journey.create_transition(None, journey.initial_state, state_map[journey_def.entry_node])
            )

        for s in journey_def.states:
            source = state_map[s.id]
            for t in s.transitions:
                target = state_map.get(t.to)
                # 注：v3.3.1 create_transition 不支持 canned_responses（转移话术走节点指南机制，
                # 留待后续）；样例定义转移级 canned_responses 为空，此处仅连 condition/to。
                created_transitions.append(
                    await journey.create_transition(
                        t.condition or None,
                        source,
                        target if target is not None else p.END_JOURNEY,
                    )
                )

        targeted = {t.to for s in journey_def.states for t in s.transitions}
        for s in journey_def.states:
            if not s.transitions and s.id not in targeted:
                created_transitions.append(
                    await journey.create_transition(None, state_map[s.id], p.END_JOURNEY)
                )
        # [评估哈希修复] 同上：补齐 transitions 使评估哈希反映真实结构
        cast(list, journey.transitions).extend(created_transitions)

        return journey

    async def _build_guidelines(
        self,
        agent: p.Agent,
        definition: AgentDefinition,
        canrep_map: dict[str, p.CannedResponseId],
        journey_map: dict[str, p.Journey],
    ) -> None:
        all_guidelines = [*definition.guidelines.guidelines, *definition.observations.observations]
        for g in all_guidelines:
            await self._create_guideline(agent, g, canrep_map, journey_map)

    async def _create_guideline(
        self,
        agent: p.Agent,
        g: GuidelineDef,
        canrep_map: dict[str, p.CannedResponseId],
        journey_map: dict[str, p.Journey],
    ) -> None:
        canreps = [canrep_map[c] for c in g.canned_responses if c in canrep_map]
        tools = [resolve_tool(t) for t in g.tools]
        kwargs: dict[str, Any] = dict(
            condition=g.condition or None,
            action=g.action or None,
            criticality=p.Criticality(g.criticality),
            priority=g.priority,
            canned_responses=canreps,
            tools=tools,
            track=g.track,
            composition_mode=_composition_mode(g.composition_mode),
        )
        if g.journey_ids and g.journey_ids[0] in journey_map:
            await journey_map[g.journey_ids[0]].create_guideline(**kwargs)
        else:
            await agent.create_guideline(**kwargs)
