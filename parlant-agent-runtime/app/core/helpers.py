"""装配共用的小工具与示例定义 IO（app.core 各模块共享）。

- `_composition_mode` / `_STATE_TYPES`：定义层枚举 → SDK 类型映射
- `_instance_suffix`：`@draft` 等实例后缀（全局存储 id 隔离，见 builder._build_journey）
- `_split_synonyms`：定义层同义词单串拆分
- `load_definition` / `DEFINITION_PATH`：本地示例定义读取（server 不可达降级路径）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import parlant.sdk as p

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
    详见 builder._build_journey docstring。追踪对账时剥掉后缀即定义层 id。
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


# 本地示例定义文件（单一事实源，仅在 server 不可达的降级路径使用）。
# 位于仓库根（agent-definition.json），相对本模块（app/core/）向上 3 级。
DEFINITION_PATH = Path(__file__).resolve().parents[3] / "agent-definition.json"


def load_definition(path: Path = DEFINITION_PATH) -> dict[str, Any]:
    """读取 agent-definition.json（本地示例定义，降级路径用）。

    main.py 启动时 server 不可达（或暂无 published）时读取；正式路径的定义
    来自 server 定义层（Mongo，parse_definition 解析成 AgentDefinition 后走
    AgentLoader.load）。原在 app/services/agent_bootstrap.py（阶段1 示例）内，
    bootstrap 移出后并入 agent_loader，拆分后归此。
    """
    return json.loads(path.read_text(encoding="utf-8"))
