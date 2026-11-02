"""评估结果语义质检（确定性规则，2026-11 评估管线加固）。

实战背景：deepseek-v4.1-flash 评估"问候与需求收集"节点时幻觉出"客户提供姓名/电话/
地址、配送 3-5 个工作日"（电商话术），next-step 选择据此判定步骤永不完成 → 旅程
静默卡死且无任何报错。此类元数据错误 schema 校验发现不了（"是个合法字符串"），
这里用确定性规则交叉比对（不引入 LLM），命中即在评估完成时响亮告警并写入
eval_status，供 server 门禁与运维观测。
"""

from __future__ import annotations

from typing import Any

# 电商/物流类幻觉关键词：出现在 customer_action 但节点定义文本（description+action）没有
# → 高度可疑（正规节点若真要求这些信息，定义文本里必然出现，不会误报）。
SUSPICIOUS_KEYWORDS = [
    "shipping address",
    "delivery",
    "business days",
    "tracking number",
    "phone number",
    "地址",
    "配送",
    "快递",
    "收货",
]


def check_journey(journey: Any, node_properties: dict[str, Any]) -> list[str]:
    """旅程评估结果质检：分叉完整性 + customer_action 幻觉模式。返回问题列表（空=通过）。"""
    issues: list[str] = []

    transitions_by_source: dict[str, list[Any]] = {}
    for t in journey.transitions or []:
        transitions_by_source.setdefault(str(t.source.id), []).append(t)

    for node in journey.states or []:
        nid = str(node.id)
        props = node_properties.get(nid) or {}
        jn = props.get("journey_node") or {}
        follow_ups = jn.get("reachable_follow_ups") or []
        outgoing = transitions_by_source.get(nid, [])

        # 分叉完整性：有出边的节点必须产出分叉条件表，否则 fork 无候选条件、旅程必卡
        if outgoing and not follow_ups:
            issues.append(f"节点[{nid}] 有 {len(outgoing)} 条出边但分叉表为空（fork 将无候选条件）")

        # 幻觉模式：customer_action 含可疑业务词而定义文本没有
        cda = props.get("customer_dependent_action_data") or {}
        customer_action = (cda.get("customer_action") or "").lower()
        if customer_action:
            node_text = f"{getattr(node, 'description', '') or ''} {getattr(node, 'action', '') or ''}".lower()
            for kw in SUSPICIOUS_KEYWORDS:
                if kw in customer_action and kw not in node_text:
                    issues.append(f"节点[{nid}] customer_action 疑幻觉：含 '{kw}' 但定义文本无此业务")

    return issues
