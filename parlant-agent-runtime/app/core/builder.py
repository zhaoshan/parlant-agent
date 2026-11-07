"""定义 → SDK 实体装配线（AgentBuilder，阶段2.3 装配逻辑的纯装配半区）。

glossary / canned / variables / journeys / guidelines / observations / relationships 逐组件
映射（映射规则见 plan/阶段2 任务 2.3）。幂等预删与评估调度不在此处——由 AgentLoader
门面编排（app/core/loader.py）。

从 app/services/agent_loader.py 拆分（2026-11），仅搬迁、逻辑零改动。
"""

from __future__ import annotations

from typing import Any, cast

import structlog
import parlant.sdk as p
from parlant.sdk import _Tag, _tool_ref_to_id
from parlant.core.common import ItemNotFoundError
from parlant.core.journeys import JourneyStore
from parlant.core.relationships import (
    RelationshipEntity,
    RelationshipEntityKind,
    RelationshipKind,
    RelationshipStore,
)

from app.models.definition import AgentDefinition, GuidelineDef, JourneyDef
from app.services.builtin_tools import BUILTIN_TOOLS, resolve_tool, set_runtime_services
from app.utils.common import escape_braces as _fmt_safe
from app.core.helpers import _STATE_TYPES, _composition_mode, _instance_suffix, _split_synonyms

logger = structlog.get_logger()


class AgentBuilder:
    """定义 -> Parlant 实体装配器（不含预删/评估调度，由门面编排）。"""

    def __init__(self, server: p.Server) -> None:
        self._server = server

    async def build(self, definition: AgentDefinition) -> tuple[p.Agent, dict[str, p.Journey]]:
        """装配定义为 SDK 实体，返回 (agent, journey_map) 供门面做评估调度。"""
        agent_def = definition.agent
        # 内置工具（variable_update 写变量）需要容器访问
        set_runtime_services(self._server.container)

        # remote 远程服务工具：按 schema 声明生成通用 HTTP 工具实例（幂等复用），
        # 供后续 tool 节点/指南绑定（resolve_tool 兜底解析，见 builtin_tools.py）。
        from app.services.http_tools import register_remote_tools

        register_remote_tools(definition.tools.tools)

        agent = await self._server.create_agent(
            id=agent_def.id,
            name=agent_def.name,
            description=self._render_description(agent_def),
            composition_mode=_composition_mode(agent_def.composition_mode),
        )
        await self._build_glossary(agent, definition)
        canrep_map = await self._build_canned(agent, definition)
        await self._build_variables(agent, definition)
        journey_map = await self._build_journeys(agent, definition)
        guideline_ids = await self._build_guidelines(agent, definition, canrep_map, journey_map)
        await self._build_observations(agent, definition, canrep_map, journey_map)
        await self._build_relationships(agent, definition, guideline_ids, set(journey_map))
        return agent, journey_map

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
            tool_ref = None
            if var.tool:
                # 变量关联工具：freshness_rules 过期时引擎以**空参数**自动调工具刷新
                # （engine.py 变量加载路径 arguments={}）→ remote 工具内核会自动注入
                # customer_id，URL 用 {customer_id} 占位即可，见 http_tools.py。
                tool_ref = resolve_tool(var.tool)
            variable = await agent.create_variable(
                name=var.name,
                description=var.description or None,
                tool=tool_ref,
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
            title=_fmt_safe(journey_def.title or journey_def.description) or "未命名旅程",
            description=_fmt_safe(journey_def.description),
            triggers=[_fmt_safe(t) for t in journey_def.triggers],
            composition_mode=_composition_mode(journey_def.composition_mode),
            priority=journey_def.priority or 0,
            id=p.JourneyId(f"{journey_def.id}{suffix}") if journey_def.id else None,
        )

        state_map: dict[str, p.JourneyState] = {}
        node_store = self._server.container[JourneyStore]
        for s in journey_def.states:
            stype = _STATE_TYPES.get(s.type, p.ChatJourneyState)
            tools = [resolve_tool(t) for t in s.tool_state]
            action = _fmt_safe(s.chat_state or s.tool_instruction) or None
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
                description=_fmt_safe(s.description or s.title) or None,
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
            # [tool→fork 修复·2026-09-28] SDK 只在 _transition()（fluent API）里为 tool 节点建
            # "journey_node_tag → tool" 的 REEVALUATION 关系；我们直接调 _create_state +
            # create_transition 绕过了它 → find_guidelines_that_need_reevaluation 反查不到
            # → 迭代2重评估返回 0 → 旅程批处理不跑 → tool 节点滞留、fork 不路由。
            # 此处按 SDK 同款（sdk.py _transition）补建，让 tool 节点的出边（含 fork）能在
            # 同轮被 next-step 选择推进。
            if tools:
                relationship_store = self._server.container[RelationshipStore]
                for t in tools:
                    await relationship_store.create_relationship(
                        source=RelationshipEntity(
                            id=_Tag.for_journey_node_id(state.id).id,
                            kind=RelationshipEntityKind.TAG_ALL,
                        ),
                        target=RelationshipEntity(
                            id=_tool_ref_to_id(t),
                            kind=RelationshipEntityKind.TOOL,
                        ),
                        kind=RelationshipKind.REEVALUATION,
                    )

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
                        _fmt_safe(t.condition) if t.condition else None,
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
    ) -> set[str]:
        """装配普通指南（Guideline），返回定义层 guideline id 集合（供 relationships 引用）。

        Observations（观察性指南）由 `_build_observations` 单独装配——Parlant 里
        观察性指南 = 无 Action 的指南（`create_observation` 是 `create_guideline` 的
        shorthand），走独立的匹配批处理（observational_batch），与普通指南语义不同。
        """
        for g in definition.guidelines.guidelines:
            await self._create_guideline(agent, g, canrep_map, journey_map, observation=False)
        return {g.id for g in definition.guidelines.guidelines} | {
            g.id for g in definition.observations.observations
        }

    async def _build_observations(
        self,
        agent: p.Agent,
        definition: AgentDefinition,
        canrep_map: dict[str, p.CannedResponseId],
        journey_map: dict[str, p.Journey],
    ) -> None:
        """装配观察性指南（Observation，无 Action）：命中即标记已发生，不要求回复动作。

        复用 `_create_guideline`（observation=True 分支走 `create_observation`）。
        """
        for g in definition.observations.observations:
            await self._create_guideline(agent, g, canrep_map, journey_map, observation=True)

    async def _create_guideline(
        self,
        agent: p.Agent,
        g: GuidelineDef,
        canrep_map: dict[str, p.CannedResponseId],
        journey_map: dict[str, p.Journey],
        *,
        observation: bool = False,
    ) -> None:
        """创建一条指南（或观察性指南），保留定义层 id（带实例后缀）。

        [2026-09-29] 保留 `gdl_*` id（原为 SDK 随机）——定义层 relationships 按
        定义层 id 引用指南，随机 id 无法被引用；@draft/多版本实例加后缀隔离（同旅程）。
        追踪对账也随之受益（指南 id 可对账定义层）。

        观察性指南（observation=True）：无 Action；`Journey.create_observation` 不接收
        `action/criticality`（Agent 版有 criticality），故参数分流。
        """
        suffix = _instance_suffix(agent.id)
        canreps = [canrep_map[c] for c in g.canned_responses if c in canrep_map]
        tools = [resolve_tool(t) for t in g.tools]
        target = journey_map.get(g.journey_ids[0]) if g.journey_ids else None
        gid = p.GuidelineId(f"{g.id}{suffix}") if g.id else None
        if observation:
            kwargs: dict[str, Any] = dict(
                condition=_fmt_safe(g.condition) or None,
                tools=tools,
                canned_responses=canreps,
                composition_mode=_composition_mode(g.composition_mode),
                id=gid,
                labels=g.labels,
                priority=g.priority,
            )
            if target is not None:
                await target.create_observation(**kwargs)
            else:
                await agent.create_observation(criticality=p.Criticality(g.criticality), **kwargs)
        else:
            kwargs = dict(
                condition=_fmt_safe(g.condition) or None,
                action=_fmt_safe(g.action) or None,
                criticality=p.Criticality(g.criticality),
                priority=g.priority,
                canned_responses=canreps,
                tools=tools,
                track=g.track,
                composition_mode=_composition_mode(g.composition_mode),
                id=gid,
                labels=g.labels,
            )
            if target is not None:
                await journey_map[g.journey_ids[0]].create_guideline(**kwargs)
            else:
                await agent.create_guideline(**kwargs)

    async def _build_relationships(
        self,
        agent: p.Agent,
        definition: AgentDefinition,
        guideline_ids: set[str],
        journey_ids: set[str],
    ) -> None:
        """装配定义层 relationships（指南/旅程/工具间的语义关系）。

        Parlant 关系图用 GUIDELINE / TAG_ALL / TOOL 三种实体（core/relationships.py）：
        - 指南/观察 id（gdl_*）→ GUIDELINE（直接映射，创建时已保留定义层 id）
        - 旅程 id（jny_*）→ 其旅程标签 TAG_ALL(journey:<id>)（与 SDK 旅程级指南同款表达）
        - 内置工具名 → TOOL（service=built-in）

        关系类型映射 RelationshipKind：蕴含/优先级/依赖/依赖任选/消歧/重评/重叠。
        所有关系带 group_id=agent.id（卸载时按 group 清理，见 unloader）。
        环检测（create_relationship 会拒绝成环）失败时定位到具体关系，不阻断加载。
        """
        suffix = _instance_suffix(agent.id)
        relationship_store = self._server.container[RelationshipStore]
        kind_map = {k.value: k for k in RelationshipKind}
        created = skipped = 0
        for rel in definition.relationships.relationships:
            src = self._resolve_relationship_entity(rel.source, guideline_ids, journey_ids, suffix)
            dst = self._resolve_relationship_entity(rel.target, guideline_ids, journey_ids, suffix)
            kind = kind_map.get((rel.kind or "").lower())
            if src is None or dst is None:
                skipped += 1
                logger.warning(
                    f"关系引用无法解析，已跳过：{rel.source} → {rel.target} [{rel.kind}]"
                    "（source/target 需为指南 id / 旅程 id / 内置工具名）"
                )
                continue
            if kind is None:
                skipped += 1
                logger.warning(
                    f"未知关系类型「{rel.kind}」已跳过（可选：{sorted(kind_map)}）"
                )
                continue
            try:
                await relationship_store.create_relationship(
                    source=src, target=dst, kind=kind, group_id=agent.id
                )
                created += 1
            except ValueError as exc:  # 环检测：create_relationship 拒绝成环
                skipped += 1
                logger.warning(
                    f"关系创建被拒（可能成环）：{rel.source} → {rel.target} [{rel.kind}]: {exc}"
                )
        logger.info(f"装配 relationships：{created} 条生效，{skipped} 条跳过")

    def _resolve_relationship_entity(
        self,
        ref: str,
        guideline_ids: set[str],
        journey_ids: set[str],
        suffix: str,
    ) -> RelationshipEntity | None:
        """把定义层引用字符串解析为引擎关系实体（GUIDELINE / TAG_ALL / TOOL）；无法识别返回 None。"""
        if not ref:
            return None
        if ref in guideline_ids:
            return RelationshipEntity(
                id=p.GuidelineId(f"{ref}{suffix}"),
                kind=RelationshipEntityKind.GUIDELINE,
            )
        if ref in journey_ids:
            return RelationshipEntity(
                id=_Tag.for_journey_id(p.JourneyId(f"{ref}{suffix}")).id,
                kind=RelationshipEntityKind.TAG_ALL,
            )
        if ref in BUILTIN_TOOLS:
            return RelationshipEntity(
                id=_tool_ref_to_id(resolve_tool(ref)),
                kind=RelationshipEntityKind.TOOL,
            )
        return None
