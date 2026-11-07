"""评估编排（AgentEvaluator）：后台评估旅程/指南 + 进度监控 + 状态登记。

零预加载后 loader 是**唯一评估器**（SDK __aexit__ 空评估表直接返回），职责：
- 旅程评估（分叉条件表 reachable_follow_ups 的唯一产出路径，详见 evaluate_journeys_now）
- 指南评估（continuous / customer_dependent_action_data 等元数据）
- 模型护栏（fail-closed，缓存 miss 且评估模型未验证 → 拒绝评估，eval_model_split）
- 语义质检（eval_quality 确定性规则，命中响亮告警）
- 评估状态登记（eval_status，server 模拟对话门禁数据源）

从 app/services/agent_loader.py 拆分（2026-11），仅搬迁、逻辑零改动。
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
import parlant.sdk as p

from app.services import eval_status
from app.patches.eval_model_split import (
    current_eval_model,
    eval_model_proven,
    proven_eval_model_markers,
)
from app.utils.eval_quality import check_journey

logger = structlog.get_logger()


class AgentEvaluator:
    """评估编排器（每个 p.Server() 一个实例即可）。"""

    def __init__(self, server: p.Server) -> None:
        self._server = server
        # 已调度过评估的指南：guideline_id -> 内容指纹（复用 SDK 内容寻址哈希）。
        # 避免 `evaluate_guidelines_now` 每次 load 遍历全量注册表把已评指南重复调度
        # （并发双写缓存 + 白烧 LLM）；内容变了指纹不同 → 照常重评（热加载/发布新版本）。
        self._guideline_eval_scheduled: dict[str, str] = {}

    def evaluate_journeys_now(self, instance_id: str, journeys: list[p.Journey]) -> None:
        """热加载旅程**后台评估**并应用节点元数据（journey_node.reachable_follow_ups 等）。

        背景：SDK 的评估-应用（_process_evaluations → _apply_single_evaluation）只在
        __aexit__ 跑一遍，服务于"启动前已加载"的实体；热加载（publish/rollback 推送、
        @draft 草稿实例）的旅程等不到它 → 节点缺 reachable_follow_ups（分叉推进的
        条件表）→ 运行期 fork 选择条件为空 → LLM 任何回答都是 'invalid condition id'
        → 旅程无法推进。故此处逐旅程评估（内容哈希缓存，未变则秒回）并应用到节点；
        entity_cq 监听节点变更会把元数据投影到节点指南。

        注意**必须后台化**：旅程评估是逐节点多次 LLM 调用（实测可达数分钟），
        阻塞会拖住 load 响应/会话创建。评估完成前 fork 暂不可推进（entry/普通节点
        不受影响）；完成时打印日志。评估失败仅影响分叉推进，不阻断加载。
        评估状态登记到 eval_status（server 模拟对话门禁 + eval_quality 语义质检）。
        """
        eval_status.mark_all_pending(instance_id, [str(j.id) for j in journeys])
        for journey in journeys:
            asyncio.create_task(self._evaluate_journey(instance_id, journey))

    async def _evaluate_journey(self, instance_id: str, journey: p.Journey) -> None:
        # —— 评估诊断日志（2026-09-27 排查草稿热加载评估）：哈希 + cache 命中预判 + 用时 + 分叉数 ——
        import time as _time

        t0 = _time.monotonic()
        _hash = ""
        cache_hit = None
        try:
            _hash = self._server._evaluator._hash_journey_evaluation_request(  # noqa: SLF001
                journey=journey
            )
            cached = await self._server._evaluator._journey_collection.find_one(  # noqa: SLF001
                {"id": {"$eq": _hash}}
            )
            cache_hit = cached is not None
        except Exception as exc:  # noqa: BLE001 - 诊断失败不影响评估
            logger.warning(f"[eval诊断] 哈希/命中预判失败 {journey.id}: {exc}")
        logger.info(
            f"[eval诊断] 旅程评估开始 id={journey.id} title={journey.title} "
            f"hash={(_hash or '?')[:8]} cache命中预判={cache_hit}"
        )
        # 模型护栏（fail-closed）：缓存 miss 且当前评估模型未验证 → 拒绝评估。
        # 防幻觉元数据落缓存；缓存热时模型无关，对话模型可随意换。
        if cache_hit is not True and not eval_model_proven():
            detail = (
                f"评估缓存未命中且当前评估模型 '{current_eval_model()}' 不在验证名单 "
                f"{proven_eval_model_markers()}——拒绝评估以防幻觉元数据落缓存；请把模型加入 "
                f"env EVAL_PROVEN_MODEL_MARKERS，或预热 evaluation_cache 后重启"
            )
            eval_status.mark(instance_id, str(journey.id), "blocked", detail=detail)
            logger.warning(f"[eval质检] 旅程评估被模型护栏阻止 id={journey.id}：{detail}")
            print(f"⛔ 旅程评估被阻止（模型护栏）：{journey.title} ({journey.id})", flush=True)
            return
        # 进度监控：评估是黑盒（实测 7-8 分钟无中间日志）；后台任务每 ~20s 读一次
        # _progress_for 打进度，避免"开始后长时间无输出像卡死"。
        monitor = asyncio.create_task(self._monitor_eval_progress("旅程", journey.id, t0))
        try:
            result = await asyncio.wait_for(
                self._server._evaluator.evaluate_journey(journey),  # noqa: SLF001
                # 1800s：零预加载后 loader 是唯一评估器（SDK __aexit__ 不再覆盖）。
                # 历史完成 433-515s；2026-11-07 SiliconFlow 免费档限流、单调用延迟翻倍
                # （14 节点串行 ≈ 840s）曾贴脸爆 900s——抬到 1800 留限流余量；
                # 超时失败会整趟重来（缓存不写入），宁可等满勿频繁重试。
                timeout=1800,
            )
            await self._server._apply_single_evaluation(  # noqa: SLF001
                "journey", journey.id, result
            )
            # 语义质检（2026-11 评估管线加固）：确定性规则交叉比对，幻觉/残缺即时响亮告警，
            # 并写入 eval_status 供 server 门禁与运维观测（不再静默卡死）。
            quality_issues = check_journey(journey, result.node_properties or {})
            eval_status.mark(instance_id, str(journey.id), "completed", issues=quality_issues)
            for q in quality_issues:
                logger.warning(f"[eval质检] 旅程评估元数据可疑 id={journey.id}：{q}")
                print(f"⚠️ [eval质检] {journey.title} ({journey.id})：{q}", flush=True)
            fu_counts = {
                nid: len(np.get("journey_node", {}).get("reachable_follow_ups") or [])
                for nid, np in (result.node_properties or {}).items()
            }
            logger.info(
                f"[eval诊断] 旅程评估完成 id={journey.id} 用时={_time.monotonic() - t0:.1f}s "
                f"分叉数={fu_counts}"
            )
            print(f"✅ 旅程评估完成：{journey.title} ({journey.id})，分叉条件表已就绪", flush=True)
        except Exception as exc:  # noqa: BLE001 - 评估失败仅影响分叉推进
            eval_status.mark(instance_id, str(journey.id), "failed", detail=f"{type(exc).__name__}: {exc}")
            logger.info(
                f"[eval诊断] 旅程评估失败 id={journey.id} 用时={_time.monotonic() - t0:.1f}s "
                f"错误={type(exc).__name__}: {exc}"
            )
            print(f"⚠️ 旅程评估失败（分叉推进可能退化）：{journey.id}: {exc}", flush=True)
        finally:
            monitor.cancel()

    def evaluate_guidelines_now(self) -> None:
        """装配后**后台**评估**新注册**的指南（continuous / customer_dependent_action_data 等）。

        背景（2026-10-22）：启动改零预加载后 SDK `__aexit__` 不再评估任何实体，而
        旅程评估只覆盖旅程 → 指南元数据无人产出 → 匹配行为退化（热加载的指南此前
        本就有此缺口）。与旅程评估同模式：create_task 后台 + 内容寻址缓存
        （内容未变秒回）；单条超时 900s。

        判重：注册表 `_guideline_evaluations` 跨 load 累积，若每次 load 全量遍历会把
        已评指南重复调度（并发双写缓存 + 白烧 LLM）。这里按**内容指纹**（复用 SDK
        `_hash_guideline_evaluation_request` = 缓存键）只评新内容：同 id 内容未变 →
        跳过；内容变（热加载/发布新版本）→ 指纹不同 → 照常重评。
        注意：注册表在 **Server**（`self._server._guideline_evaluations`），不在
        `_evaluator` 上——误访问 `_evaluator._guideline_evaluations` 会 AttributeError，
        且会触发 load() 回滚删实体、殃及已调度的旅程评估任务（2026-10-22 踩过）。
        """
        evaluator = self._server._evaluator  # noqa: SLF001
        for guideline_id, (args, func) in list(
            self._server._guideline_evaluations.items()  # noqa: SLF001
        ):
            try:
                # args = (guideline_id, GuidelineContent, tool_ids)；flags 用评估默认 False/True
                fp = evaluator._hash_guideline_evaluation_request(  # noqa: SLF001
                    args[1], args[2], False, True
                )
            except Exception:  # noqa: BLE001 - 指纹失败退化为按 id 判重
                fp = str(args)
            if self._guideline_eval_scheduled.get(guideline_id) == fp:
                continue  # 同内容已调度过，不再重复评估
            self._guideline_eval_scheduled[guideline_id] = fp
            asyncio.create_task(self._evaluate_guideline(guideline_id, args, func))

    async def _evaluate_guideline(self, guideline_id: str, args: tuple, func: Any) -> None:
        """单条指南后台评估 + 应用（结果写入指南 metadata）。失败仅影响该条指南元数据。"""
        import time as _time

        t0 = _time.monotonic()
        # 模型护栏（同旅程，fail-closed）：缓存 miss 且模型未验证 → 拒绝评估，防幻觉元数据落缓存
        try:
            _gh = self._server._evaluator._hash_guideline_evaluation_request(  # noqa: SLF001
                args[1], args[2], False, True
            )
            _g_cached = await self._server._evaluator._guideline_collection.find_one(  # noqa: SLF001
                {"id": {"$eq": _gh}}
            )
        except Exception:  # noqa: BLE001 - 预判失败按未命中处理，交护栏决定
            _g_cached = None
        if _g_cached is None and not eval_model_proven():
            logger.warning(
                f"[eval质检] 指南评估被模型护栏阻止 id={guideline_id}"
                f"（缓存未命中且评估模型 '{current_eval_model()}' 未验证）"
            )
            return
        monitor = asyncio.create_task(self._monitor_eval_progress("指南", guideline_id, t0))
        try:
            result = await asyncio.wait_for(func(*args), timeout=900)
            await self._server._apply_single_evaluation(  # noqa: SLF001
                "guideline", guideline_id, result
            )
            if not (result.properties or {}):
                logger.warning(f"[eval质检] 指南评估产出空元数据 id={guideline_id}")
            logger.info(
                f"[eval诊断] 指南评估完成 id={guideline_id} 用时={_time.monotonic() - t0:.1f}s"
            )
        except Exception as exc:  # noqa: BLE001 - 指南评估失败不影响装配/其它指南
            logger.warning(f"[eval诊断] 指南评估失败 {guideline_id}: {type(exc).__name__}: {exc}")
        finally:
            monitor.cancel()

    async def _monitor_eval_progress(self, kind: str, entity_id: str, t0: float) -> None:
        """评估期间定期打进度日志：进度变化即打；进度到顶但任务未结束（LLM 编译收尾）打标注。

        SDK `_CachedEvaluator` 每 0.5s 轮询评估任务时更新 `_progress_for(entity_id)`——
        它是 stretch/increment 检查点计数，会**提前到 100%**（其后相对动作/分叉计算不再
        更新它），故到顶后打"收尾中"标注避免像卡死。评估结束由调用方 finally 取消。
        """
        import time as _time

        last_pct: float | None = None
        last_log = 0.0
        while True:
            await asyncio.sleep(20)
            try:
                pct = self._server._evaluator._progress_for(entity_id)  # noqa: SLF001
            except Exception:  # noqa: BLE001 - 监控失败不影响评估
                return
            now = _time.monotonic()
            if pct >= 99.9:
                # 进度到顶但任务未完成 = 评估收尾（RelativeActionProposer / 可达分叉计算）
                if (now - last_log) >= 60:
                    logger.info(
                        f"[eval诊断] {kind}评估收尾中 id={entity_id} 进度=100% "
                        f"已用时={now - t0:.0f}s（相对动作/分叉计算，进度到顶非卡死）"
                    )
                    last_log = now
                last_pct = pct
                continue
            changed = last_pct is None or abs(pct - last_pct) >= 1.0
            if changed or (now - last_log) >= 60:
                logger.info(
                    f"[eval诊断] {kind}评估进度 id={entity_id} 进度={pct:.0f}% 已用时={now - t0:.0f}s"
                )
                last_log = now
            last_pct = pct
