"""journey index → 节点名称 解析（替代 parlant `entity_cq.journey_node_labels()` 插桩）。

journey 观测日志（journey.progress 等）路径里的数字是 parlant 引擎**投影指南**
metadata 的 ``journey_node.index``——BFS 分配序号，不是节点 id。分配算法见 parlant
`core/journey_guideline_projection.py`：从 `journey.root_id` 出发按出边顺序 BFS，
节点首次出队即分配 index=1,2,…；出边顺序 = store 里边的创建顺序（loader 建边顺序 =
root→entry 先、再按 definition `states[].transitions` 顺序）。

这里在 runtime 侧用**定义层数据**（`definition.journeys[].states[]/transitions/entry_node`）
复刻同一 BFS，产出 ``{index: 名称}``。名称**优先取 `state.title`**（短标签，如「风险测评」），
回退 `state.description`（与 loader 存进引擎的 `node.description = s.description or s.title`
一致，见 agent_loader._build_journey），截断 12 字。

> 不缓存：journey 节点数少（<20），每次 BFS 开销可忽略；且热更新同 id 改结构时免缓存失效问题。
"""

from collections import deque

from app.models import AgentDefinition
from app.models.definition import JourneyDef

_MAX_LEN = 12

# loader 建 journey 时的初始状态（SDK 自动建的根节点，`journey.root_id`），无名称。
# 它在投影 BFS 里分配 index=1，并有一条根→entry_node 的边（loader `create_transition(None, initial, entry)`）。
_ROOT_ID = "__root__"


def _truncate(label: str) -> str:
    return label if len(label) <= _MAX_LEN else label[: _MAX_LEN - 1] + "…"


def journey_labels(journey: JourneyDef) -> dict[str, str]:
    """按 parlant 投影同款 BFS 复刻 ``{index: 节点名称}``。

    index 从 1 开始（root 为 1，entry_node 为 2，其后按出边顺序 BFS）。
    自环/已访问边跳过（visited 按 (边, 目标节点) 对，与 parlant 一致）。
    """
    node_edges: dict[str, list[tuple[str | None, str]]] = {_ROOT_ID: []}
    node_edges[_ROOT_ID].append((None, journey.entry_node))
    for s in journey.states:
        node_edges[s.id] = [(t.transition_id or t.condition or "", t.to) for t in s.transitions]

    by_id = {s.id: s for s in journey.states}

    def name_of(node_id: str) -> str:
        if node_id == _ROOT_ID:
            return ""
        state = by_id.get(node_id)
        if not state:
            return ""
        return (state.title or state.description or "").strip()

    index = 0
    indexes: dict[str, int] = {}
    labels: dict[str, str] = {}
    queue: deque[tuple[str | None, str]] = deque([(None, _ROOT_ID)])
    visited: set[tuple[str | None, str]] = set()

    while queue:
        edge_id, node_id = queue.popleft()
        if node_id not in indexes:
            index += 1
            indexes[node_id] = index
            label = name_of(node_id) or f"node{index}"
            labels[str(index)] = _truncate(label)
        for child_edge_id, child in node_edges.get(node_id, []):
            if (child_edge_id, child) in visited:
                continue
            queue.append((child_edge_id, child))
            visited.add((child_edge_id, child))
        visited.add((edge_id, node_id))

    return labels


class JourneyLabelResolver:
    """按引擎 journey id（含实例后缀，如 `jny_xxx@draft`）解析定义层 journey 的 index→名称。"""

    def labels(
        self,
        journey_key: str,
        definition: AgentDefinition | None,
    ) -> dict[str, str]:
        if definition is None:
            return {}
        base_id = journey_key.split("@")[0]
        for j in definition.journeys.journeys:
            if j.id == base_id:
                return journey_labels(j)
        return {}
