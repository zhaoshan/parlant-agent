"""评估状态登记处：旅程评估就绪状态（模拟对话门禁 + 失败快速暴露）。

背景（2026-11 评估管线加固）：
- 零预加载后评估全走 loader 后台任务，"旅程分叉表是否就绪"此前无任何可查询状态——
  模拟对话可能在分叉缺失时发起 → 旅程静默卡死（10-21 投顾卡节点 3 事故）；
- 这里按**实例**（published 无后缀 / @draft 带后缀）登记每个旅程的评估状态，server
  建模拟会话前经 `GET /internal/agents/{id}/eval-status` 查询，未就绪则拒绝（409）。

状态语义：
- pending   已调度/评估中（loader create_task 时置位）
- completed 评估完成（issues = eval_quality 语义质检告警，非空也属完成，仅告警）
- failed    评估异常（超时/错误）
- blocked   模型护栏拒绝：缓存 miss 且当前对话模型不在验证名单——宁可不评也不让
            幻觉元数据落缓存（fail-closed，对话模型可随意换的前提）
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class JourneyEval:
    status: str  # pending / completed / failed / blocked
    issues: list[str] = field(default_factory=list)
    detail: str = ""


# instance_id → {journey_id: JourneyEval}（进程内瞬态：重启后随重新加载重建）
_ENTRIES: dict[str, dict[str, JourneyEval]] = {}
_LOCK = threading.Lock()


def mark(instance_id: str, journey_id: str, status: str, issues: list[str] | None = None, detail: str = "") -> None:
    with _LOCK:
        _ENTRIES.setdefault(instance_id, {})[journey_id] = JourneyEval(status=status, issues=issues or [], detail=detail)


def mark_all_pending(instance_id: str, journey_ids: list[str]) -> None:
    with _LOCK:
        entry = _ENTRIES.setdefault(instance_id, {})
        for jid in journey_ids:
            entry[jid] = JourneyEval(status="pending")


def drop_instance(instance_id: str) -> None:
    with _LOCK:
        _ENTRIES.pop(instance_id, None)


def get_status(instance_id: str) -> dict:
    """server 门禁查询：ready = 全部旅程 completed（无旅程 = 就绪）+ 明细/汇总。"""
    with _LOCK:
        journeys = {
            jid: {"status": e.status, "issues": e.issues, "detail": e.detail}
            for jid, e in _ENTRIES.get(instance_id, {}).items()
        }
    summary: dict[str, int] = {"pending": 0, "completed": 0, "failed": 0, "blocked": 0}
    for j in journeys.values():
        summary[j["status"]] = summary.get(j["status"], 0) + 1
    ready = all(j["status"] == "completed" for j in journeys.values()) if journeys else True
    return {"agent_id": instance_id, "ready": ready, "journeys": journeys, "summary": summary}
