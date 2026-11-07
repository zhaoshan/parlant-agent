"""旅程评估缓存键的稳定结构签名（monkey-patch `_CachedEvaluator._hash_journey_evaluation_request`）。

上游哈希含 `edge.id`，而 SDK 每次加载给 edge 生成随机 id → 键随重启漂移 → 旅程评估缓存
永不命中。本 patch 换成稳定签名：`journey.id` + node ids + 排序的
`(source.id, target.id, condition)` 三元组，排除随机 edge.id。

边界（与上游一致，未收紧内容维度）：增删节点/边、改转移条件 → 新键 → 重评估；节点 id 与
条件不变、仅改 action/description 文案 → 键不变 → 命中缓存（内容盲是上游原生行为）。
须在 p.Server 装配前幂等安装（入口 `app.main.install_runtime_patches`）。
"""

from __future__ import annotations

import structlog
from typing import Any

import xxhash

logger = structlog.get_logger()

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

    from app.patches.patch_guard import assert_anchor

    assert_anchor(_CachedEvaluator, "_hash_journey_evaluation_request", patch="journey-hash-stable",
                  hint="上游若哈希已稳定（不含随机 edge id），可删除本 patch。")
    _CachedEvaluator._hash_journey_evaluation_request = _stable_hash_journey
    _PATCHED = True
    logger.info("[journey-hash] 已安装稳定结构签名 patch（排除随机 edge.id，重启命中缓存）")