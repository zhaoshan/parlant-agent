"""阶段2.1：agent-definition.json 的 pydantic 模型 + 校验。

依据 agent-definition.json 提炼 Schema（见 plan/阶段2 任务 2.1）。设计原则：
- 全字段可选、extra="ignore"：样本里有大量空/可空字段（relationships/observations/
  experience_criteria 等），Schema 只约束 loader 真正消费的字段，其余容忍。
- 字段名与 JSON 一致（都是 snake_case），无需 alias。
- 校验集中在值语义（枚举取值、id 引用），报错信息清晰。

与 Parlant 实体的映射关系见 app/loader.py（阶段2.3 通用转换器）。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


# ---------------------------------------------------------------- agent
class Boundary(_Base):
    allowed: list[str] = Field(default_factory=list)
    prohibited: list[str] = Field(default_factory=list)
    emergency_action: str = ""


class Utterances(_Base):
    greeting: list[str] = Field(default_factory=list)
    preamble: list[str] = Field(default_factory=list)
    system_error_fallback: str = ""
    timeout_fallback: str = ""


class AgentDef(_Base):
    id: str
    name: str = ""
    description: str = ""
    composition_mode: str = "fluid"
    default_language: str = "zh-CN"
    version: str = "1.0.0"
    boundary: Boundary = Field(default_factory=Boundary)
    utterances: Utterances = Field(default_factory=Utterances)
    preamble: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- glossary / canned / variable
class TermDef(_Base):
    id: str
    name: str
    description: str = ""
    synonyms: list[str] | str = Field(default_factory=list)
    bound_to: str = ""
    tags: list[str] = Field(default_factory=list)


class CannedResponseDef(_Base):
    id: str
    template: str = ""
    title: str = ""
    signals: list[str] = Field(default_factory=list)
    usage_context: str = ""
    bound_to: str = ""
    field_dependencies: list[str] = Field(default_factory=list)
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class VariableDef(_Base):
    id: str
    name: str
    type: str = "string"
    description: str = ""
    default_value: Any = None
    freshness_rules: str | None = None
    tool: str = ""
    allowed_values: list[Any] = Field(default_factory=list)
    bound_to: str = ""


class Glossary(_Base):
    glossary: list[TermDef] = Field(default_factory=list)


class CannedResponses(_Base):
    responses: list[CannedResponseDef] = Field(default_factory=list)


class Variables(_Base):
    variables: list[VariableDef] = Field(default_factory=list)


# ---------------------------------------------------------------- guideline / journey
class GuidelineDef(_Base):
    id: str
    condition: str = ""
    action: str = ""
    description: str = ""
    criticality: str = "medium"
    priority: int = 0
    enabled: bool = True
    track: bool = True
    composition_mode: str = "fluid"
    journey_ids: list[str] = Field(default_factory=list)
    canned_responses: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    variable_conditions: list[Any] = Field(default_factory=list)
    variable_updates_on_match: list[Any] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)

    @field_validator("criticality")
    @classmethod
    def _check_criticality(cls, v: str) -> str:
        if v.lower() not in {"low", "medium", "high"}:
            raise ValueError(f"criticality 取值须为 low/medium/high，收到 '{v}'")
        return v.lower()


class TransitionDef(_Base):
    transition_id: str = ""
    condition: str = ""
    to: str = ""
    timeout_branch: bool = False
    canned_responses: list[str] = Field(default_factory=list)
    variable_conditions: list[Any] = Field(default_factory=list)


class StateDef(_Base):
    id: str
    type: Literal["chat", "tool", "fork"] = "chat"
    title: str = ""
    description: str = ""
    chat_state: str = ""
    tool_instruction: str = ""
    tool_state: list[str] = Field(default_factory=list)
    composition_mode: str = "fluid"
    priority: int = 0
    canned_responses: list[str] = Field(default_factory=list)
    transitions: list[TransitionDef] = Field(default_factory=list)
    variable_updates_on_enter: list[Any] = Field(default_factory=list)
    variable_updates_on_exit: list[Any] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)


class JourneyDef(_Base):
    id: str
    title: str = ""
    description: str = ""
    entry_node: str = ""
    triggers: list[str] = Field(default_factory=list)
    composition_mode: str = "fluid"
    priority: int = 0
    states: list[StateDef] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)

    @field_validator("states")
    @classmethod
    def _check_entry_node(cls, v: list[StateDef], info: Any) -> list[StateDef]:
        entry = info.data.get("entry_node")
        if entry and all(s.id != entry for s in v):
            raise ValueError(f"entry_node '{entry}' 不在 states[] 中")
        return v


class Guidelines(_Base):
    guidelines: list[GuidelineDef] = Field(default_factory=list)


class Journeys(_Base):
    journeys: list[JourneyDef] = Field(default_factory=list)


# ---------------------------------------------------------------- tools / retrievers / misc
class ToolDef(_Base):
    id: str
    name: str = ""
    type: str = "builtin"
    source: str = "builtin"
    description: str = ""
    timeout_seconds: float = 30.0
    consequential: bool = True
    input_schema: dict[str, Any] = Field(default_factory=dict)


class Tools(_Base):
    tools: list[ToolDef] = Field(default_factory=list)


class RetrieverDef(_Base):
    id: str
    type: str = "ragflow_http"
    title: str = ""
    description: str = ""
    top_k: int = 5
    min_score: Any = None
    endpoint: str = ""
    collection: str = ""
    status: str = "active"
    global_: bool = Field(default=True, alias="global")


class Retrievers(_Base):
    initialized: bool = False
    context_min_score_default: Any = 0.3
    retrievers: list[RetrieverDef] = Field(default_factory=list)


class RelationshipDef(_Base):
    id: str = ""
    source: str = ""
    target: str = ""
    kind: str = ""


class Relationships(_Base):
    relationships: list[RelationshipDef] = Field(default_factory=list)


class Observations(_Base):
    observations: list[GuidelineDef] = Field(default_factory=list)


# ---------------------------------------------------------------- 顶层定义
class AgentDefinition(_Base):
    """顶层 agent-definition.json，覆盖 loader 消费的全部组件。"""

    agent: AgentDef
    glossary: Glossary = Field(default_factory=Glossary)
    canned_responses: CannedResponses = Field(default_factory=CannedResponses)
    variables: Variables = Field(default_factory=Variables)
    guidelines: Guidelines = Field(default_factory=Guidelines)
    journeys: Journeys = Field(default_factory=Journeys)
    tools: Tools = Field(default_factory=Tools)
    retrievers: Retrievers = Field(default_factory=Retrievers)
    relationships: Relationships = Field(default_factory=Relationships)
    observations: Observations = Field(default_factory=Observations)


def parse_definition(data: dict[str, Any]) -> AgentDefinition:
    """解析并校验一份定义；失败抛出 pydantic.ValidationError（含清晰路径）。"""
    return AgentDefinition.model_validate(data)