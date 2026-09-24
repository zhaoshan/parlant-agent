"""阶段1.3：手动装载示例"提前结清"Agent（definition -> Parlant 实体逐字段映射）。

把 agent-definition.json 的每个字段亲手映射到 Parlant 实体，是理解 schema 与
引擎关系的最佳实践（见 plan/阶段1-runtime最小可用-单Agent对话与追踪.md 任务 1.3）。阶段2 起本模块的
映射逻辑被 AgentLoader 取代（本文件退化为「单 agent 的手工装配示例」）。

字段映射（与 Parlant v3.3.1 SDK 对齐）：
  agent              -> Agent（name/description/composition_mode；boundary/utterances
                        无对应实体，折叠进 description）
  glossary[]         -> Term（synonyms 定义层是逗号拼接单串，需拆成列表）
  canned_responses[] -> CannedResponse（保留 def_id -> CannedResponseId 供指南引用）
  variables[]        -> Variable + set_value_for_agent(default_value)
                        （type 仅定义层约束，引擎值就是 JSON，按 type 透传）
  guidelines[]       -> Guideline；带 journey_ids 的挂到对应 Journey（journey-level
                        guideline），否则挂到 Agent。criticality/priority/canned_responses
                        直接映射
  journeys[]         -> Journey + 状态图：
                        state.type chat/tool/fork -> Chat/Tool/ForkJourneyState
                        state.chat_state/tool_instruction -> action
                        state.tool_state[] -> 工具名解析成 ToolRef
                        transitions[].condition -> transition.condition；叶子状态接 END_JOURNEY
  tools[] (builtin)  -> app.services.builtin_tools 用 @p.tool 实现同名工具，按名解析

注意：状态图用 Journey._create_state + Journey.create_transition 装配（后者是公开
API；前者虽带下划线但是唯一支持「先建状态再连线」的入口，且能保留定义层状态 id）。
已锁定本地源码版本，升级 Parlant 时需复核。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import parlant.sdk as p

from app.services.builtin_tools import resolve_tool

DEFINITION_PATH = Path(__file__).resolve().parents[3] / "agent-definition.json"

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


def load_definition(path: Path = DEFINITION_PATH) -> dict[str, Any]:
    """读取 agent-definition.json（单一事实源）。"""
    return json.loads(path.read_text(encoding="utf-8"))


def _composition_mode(value: str | None) -> p.CompositionMode:
    return _COMPOSITION_MODES.get((value or "fluid").lower(), p.CompositionMode.FLUID)


def _criticality(value: str | None) -> p.Criticality:
    try:
        return p.Criticality((value or "medium").lower())
    except ValueError:
        return p.Criticality.MEDIUM


def _split_synonyms(raw: Any) -> list[str]:
    """定义层 synonyms 是逗号拼接的单串（如 ["a,b,c"]），拆成列表。"""
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [raw]
    out: list[str] = []
    for item in raw:
        out.extend(s.strip() for s in str(item).split(",") if s.strip())
    return out


async def _build_glossary(agent: p.Agent, definition: dict[str, Any]) -> None:
    for term in definition.get("glossary", {}).get("glossary", []):
        await agent.create_term(
            name=term["name"],
            description=term.get("description", ""),
            synonyms=_split_synonyms(term.get("synonyms")),
        )


async def _build_canned_responses(
    agent: p.Agent, definition: dict[str, Any]
) -> dict[str, p.CannedResponseId]:
    """建预设话术，返回 def_id -> CannedResponseId 映射（指南引用用）。"""
    id_map: dict[str, p.CannedResponseId] = {}
    for rsp in definition.get("canned_responses", {}).get("responses", []):
        cid = await agent.create_canned_response(
            template=rsp.get("template", ""),
            signals=rsp.get("signals", []) or [],
        )
        id_map[rsp["id"]] = cid
    return id_map


async def _build_variables(agent: p.Agent, definition: dict[str, Any]) -> None:
    for var in definition.get("variables", {}).get("variables", []):
        variable = await agent.create_variable(
            name=var["name"],
            description=var.get("description") or None,
            freshness_rules=var.get("freshness_rules") or None,
        )
        # default_value 按定义层 type 透传（JSON 原生类型）
        await variable.set_value_for_agent(agent, var.get("default_value"))


async def _build_journey(
    agent: p.Agent, journey_def: dict[str, Any]
) -> tuple[p.Journey, dict[str, p.JourneyStateId]]:
    """装配一个旅程的状态图，返回 (Journey, def_state_id -> 实际状态id)。

    先建全部状态（保留定义层状态 id），再连 transitions，最后把叶子接 END_JOURNEY。
    """
    journey = await agent.create_journey(
        title=journey_def.get("title") or journey_def.get("description") or "未命名旅程",
        description=journey_def.get("description", ""),
        triggers=journey_def.get("triggers") or [],
        composition_mode=_composition_mode(journey_def.get("composition_mode")),
    )

    states_def = journey_def.get("states", [])
    state_map: dict[str, p.JourneyState] = {}

    # 1) 建全部状态
    for s in states_def:
        stype = _STATE_TYPES.get(s.get("type", "chat"), p.ChatJourneyState)
        tools = [resolve_tool(t) for t in (s.get("tool_state") or [])]
        # action 优先 chat_state；tool 类型用 tool_instruction（或 chat_state 兜底）
        action = s.get("chat_state") or s.get("tool_instruction") or None
        state_map[s["id"]] = await journey._create_state(  # noqa: SLF001 见模块 docstring
            stype,
            action=action,
            description=s.get("description") or s.get("title") or None,
            tools=tools,
            id=p.JourneyStateId(s["id"]),
            labels=s.get("labels") or (),
        )

    # 2) 入口：initial_state -> entry_node（无条件）
    entry_id = journey_def.get("entry_node")
    if entry_id and entry_id in state_map:
        await journey.create_transition(None, journey.initial_state, state_map[entry_id])

    # 3) transitions
    for s in states_def:
        source = state_map[s["id"]]
        for t in s.get("transitions", []):
            target = state_map.get(t.get("to"))
            await journey.create_transition(
                t.get("condition") or None,
                source,
                target if target is not None else p.END_JOURNEY,
            )

    # 4) 叶子状态（无出边）接 END_JOURNEY，显式收尾
    targeted = {t.get("to") for s in states_def for t in s.get("transitions", [])}
    for s in states_def:
        if not s.get("transitions") and s["id"] not in targeted:
            await journey.create_transition(None, state_map[s["id"]], p.END_JOURNEY)

    return journey, {sid: st.id for sid, st in state_map.items()}


async def _build_guidelines(
    agent: p.Agent,
    definition: dict[str, Any],
    canrep_map: dict[str, p.CannedResponseId],
    journey_map: dict[str, p.Journey],
) -> None:
    for g in definition.get("guidelines", {}).get("guidelines", []):
        canreps = [canrep_map[c] for c in (g.get("canned_responses") or []) if c in canrep_map]
        tools = [resolve_tool(t) for t in (g.get("tools") or [])]
        kwargs: dict[str, Any] = dict(
            condition=g.get("condition") or None,
            action=g.get("action") or None,
            criticality=_criticality(g.get("criticality")),
            priority=g.get("priority", 0),
            canned_responses=canreps,
            tools=tools,
            track=g.get("track", True),
            composition_mode=_composition_mode(g.get("composition_mode")),
        )
        journey_ids = g.get("journey_ids") or []
        if journey_ids and journey_ids[0] in journey_map:
            # 挂到旅程下：仅当该旅程激活时生效
            await journey_map[journey_ids[0]].create_guideline(**kwargs)
        else:
            await agent.create_guideline(**kwargs)


async def bootstrap_sample_agent(server: p.Server) -> p.Agent:
    """将示例定义装载进运行中的 p.Server()，返回装配好的 Agent。"""
    definition = load_definition()
    agent_def = definition["agent"]

    # 描述折叠 boundary/utterances（Parlant 无对应实体）
    description = agent_def.get("description", "")
    boundary = agent_def.get("boundary") or {}
    if boundary.get("prohibited"):
        description += "\n禁止事项：" + "；".join(boundary["prohibited"])
    if agent_def.get("default_language"):
        description += f"\n（默认语言：{agent_def['default_language']}）"

    agent = await server.create_agent(
        id=agent_def["id"],  # 用定义层 id，保证跨重启稳定（Registry 依赖）
        name=agent_def["name"],
        description=description,
        composition_mode=_composition_mode(agent_def.get("composition_mode")),
    )

    await _build_glossary(agent, definition)
    canrep_map = await _build_canned_responses(agent, definition)
    await _build_variables(agent, definition)

    # 先建旅程（指南可能引用），再建指南
    journey_map: dict[str, p.Journey] = {}
    for j in definition.get("journeys", {}).get("journeys", []):
        journey, _ = await _build_journey(agent, j)
        journey_map[j["id"]] = journey

    await _build_guidelines(agent, definition, canrep_map, journey_map)

    return agent
