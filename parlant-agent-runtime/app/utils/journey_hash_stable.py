"""旅程评估哈希稳定签名（根治随机 edge id 导致每次重启重评估）。

背景（2026-10-21 定位）：SDK `_hash_journey_evaluation_request` 用 `edge.id` 参与哈希，而
`create_transition/create_edge`（及 loader 直调）每次加载给 edge 生成**随机 id** → 同一旅程每次
重启哈希都变 → journey 评估缓存永不命中（guideline 是内容寻址、正常命中；journey 每次都重评估）。

修复：monkey-patch 成**稳定结构签名**——`journey.id` + 排序后的 node ids + 排序后的
`(source, target, condition)` 三元组，**排除随机 edge.id**。结构一变哈希仍变（变更感知保留），
结构不变则跨重启稳定命中缓存。

遵循项目"hack 归 runtime 持有"（同 `app/utils/observability.py` / `atomic_json_file.py`）：
不改 parlant 源码，运行时装配期幂等安装。
"""

from __future__ import annotations

import logging
from typing import Any

import xxhash

logger = logging.getLogger(__name__)

_PATCHED = False


def _stable_hash_journey(self: Any, journey: Any) -> str:
    """稳定结构签名：journey.id + 排序 node ids + 排序 (source.id:target.id:condition)。"""
    node_ids_str = (
        ",".join(str(node.id) for node in journey.states) if journey.states else ""
    )
    edges = [
        # source/target 是 JourneyState 对象（非 id），取 .id；condition 为 str|None
        f"{edge.source.id}:{edge.target.id}:{edge.condition or ''}"
        for edge in journey.transitions
    ]
    edges_str = ",".join(sorted(edges)) if edges else ""
    return xxhash.xxh3_128_hexdigest(
        f"{journey.id}:{node_ids_str}:{edges_str}".encode()
    )


def install_stable_journey_hash() -> None:
    """幂等安装：替换 `_CachedEvaluator._hash_journey_evaluation_request` 为稳定签名版。"""
    global _PATCHED
    if _PATCHED:
        return
    from parlant.sdk import _CachedEvaluator

    _CachedEvaluator._hash_journey_evaluation_request = _stable_hash_journey
    _PATCHED = True
    logger.info("[journey-hash] 已安装稳定结构签名 patch（排除随机 edge.id，重启命中缓存）")