"""journey 评估生成条件花括号转义：模型生成的 reachable_follow_ups 条件回填前转义。

背景（2026-11-07 实测，agent-167c28）：
旅程节点 action 经 loader `escape_braces` 转义后存图（`{{order_status}}`），评估 prompt
经 `.format()` 渲染后模型看到的是 `{order_status}`，原样抄进自己生成的
`condition_to_child_then_to_path`。该生成文本被 SDK 直接 f-string 拼进**父节点**的
prompt section 模板，再经 PromptBuilder `template.format(**props)`（props 常为 {}）→
单花括号被当格式占位符 → `KeyError: 'order_status'` → 该节点 3 次重试全挂 →
`reachable_follow_ups` 残缺 → fork 不推进（见 doc03 §3/§8 同类问题的评估侧变体）。

修复点：patch `do_node_evaluation` 返回后，对模型生成的 `_ReachableFollowUps.condition`
就地转义（`{`→`{{`）。同一 list 对象已被 SDK 存进 `new_graph[node].reachable_follow_ups`
供父节点 prompt 使用，就地改属性两者同时生效；最终进入评估缓存/引擎注入的条件文本
与 loader 转义约定一致（引擎 prompt 同样经 `.format`，渲染回单花括号，LLM 所见不变）。

上游 bug（应贡献上游）：SDK 把 LLM 自由生成文本拼进 `.format()` 模板却不转义。
上游修复后可删除本 patch（锚点缺失时 patch_guard 会响亮失败提醒）。
"""

from __future__ import annotations

from app.utils.common import escape_braces

_installed = False
_orig_do_node_evaluation = None  # install_journey_eval_braces_patches() 里保存原方法


async def _patched_do_node_evaluation(self, new_graph, node_idx, children_info):
    result = await _orig_do_node_evaluation(self, new_graph, node_idx, children_info)
    # 生成文本可能含单花括号占位符（模型抄录定义文本），回填父节点 prompt 前统一转义
    for r in result:
        if r.condition and ("{" in r.condition or "}" in r.condition):
            r.condition = escape_braces(r.condition)
    return result


def install_journey_eval_braces_patches() -> None:
    """旅程评估生成条件花括号转义（幂等）。

    经 app.main.install_runtime_patches() 在 p.Server 装配前统一调用（类级 patch）。
    """
    global _installed, _orig_do_node_evaluation
    if _installed:
        return

    from parlant.core.services.indexing.journey_reachable_nodes_evaluation import (
        JourneyReachableNodesEvaluator,
    )

    from app.patches.patch_guard import assert_anchor

    assert_anchor(
        JourneyReachableNodesEvaluator,
        "do_node_evaluation",
        patch="journey-eval-braces",
        hint="上游若已自行转义生成条件（或不再 f-string 拼模板）可删除本 patch。",
    )

    _orig_do_node_evaluation = JourneyReachableNodesEvaluator.do_node_evaluation
    JourneyReachableNodesEvaluator.do_node_evaluation = _patched_do_node_evaluation
    _installed = True
