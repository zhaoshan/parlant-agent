"""EngineHooks 观测装配（替代 parlant 源码的 journey.progress / engine.reeval /
engine.not_prepared 与 process 根 span I/O 插桩，见 docs/06-dev-process/05 §2.2）。

- ``journey_progress_log``：挂 `on_preparation_iteration_end`——每次准备迭代结束
  打印 `[parlant-agent] journey.progress`（session + 迭代号 + 各旅程 **index:名称** 路径）。
  原 engine.py 插桩在同一时机（`_run_preparation_iteration` 后）取 `state.journey_paths`，
  这里用官方 EngineHooks，零 parlant 源码改动。
- ``_process_span_io``：同一回调内用 `trace.get_current_span()` 取到 process 根 span
  （parlant `OpenTelemetryTracer.span` 用 `trace.use_span` 管理 current，opentelemetry.py:186，
  回调在 process span 作用域内运行）→ 设 `langfuse.observation.input/output`，
  替代原 engine.py:209 的 process 根 span I/O 插桩。

诊断信息派生（doc05 §2.4）：REEVALUATION 是否生效看路径是否推进；executed_tools 看
`state.iterations[-1].executed_tools`；tool 节点命中看路径尾节点 type（runtime 有 definition）。
"""

from typing import Any, Optional

from opentelemetry import trace
from parlant.core.engines.alpha.engine_context import EngineContext
from parlant.core.engines.alpha.hooks import EngineHookResult, EngineHooks

from app.services import get_runtime

from app.observability.labels.journey_labels import JourneyLabelResolver

_resolver = JourneyLabelResolver()


def _fmt_index(labels: dict[str, str], idx: str) -> str:
    return f"{idx}:{labels.get(idx, '?')}"


def _process_span_io(context: EngineContext) -> None:
    """process 根 span 的 I/O 摘要（等价原 engine.py:209 插桩）。"""
    span = trace.get_current_span()
    if span is None or not span.is_recording():
        return

    # input = 本条客户消息
    if msg := context.interaction.last_customer_message:
        span.set_attribute("langfuse.observation.input", msg.content)

    # output = 本轮已生成的 agent 消息（多轮拼接）
    outs = [
        str(e.data.get("message"))
        for e in context.state.message_events
        if getattr(e, "kind", None) is not None
        and e.kind.name == "MESSAGE"
        and e.data.get("message")
    ]
    if outs:
        span.set_attribute("langfuse.observation.output", "\n".join(outs))


async def _journey_progress_log(
    context: EngineContext,
    payload: Any = None,
    exc: Optional[Exception] = None,
) -> EngineHookResult:
    """旅程推进观测日志（index:名称）；观测失败不影响主链路。"""
    try:
        state = context.state
        if not state.journey_paths:
            return EngineHookResult.CALL_NEXT

        # agent id 带实例后缀（@draft）；registry 按定义 id（无后缀）存定义
        agent_base = context.agent.id.split("@")[0]
        definition = get_runtime().registry.definition(agent_base)

        paths = {
            str(jid): [
                _fmt_index(_resolver.labels(str(jid), definition), n) if n else None
                for n in path
            ]
            for jid, path in state.journey_paths.items()
        }
        context.logger.info(
            f"[parlant-agent] journey.progress session={context.info.session_id} "
            f"iter={len(state.iterations)} paths={paths}"
        )

        # 诊断派生：未准备原因（executed_tools / tool 节点命中）
        if state.iterations:
            last = state.iterations[-1]
            if last.executed_tools:
                context.logger.info(
                    f"[parlant-agent] engine.not_prepared session={context.info.session_id} "
                    f"iter={len(state.iterations)} "
                    f"executed_tools={[t.to_string() for t in last.executed_tools]}"
                )

        _process_span_io(context)
    except Exception:  # noqa: BLE001 观测失败不阻断引擎
        pass
    return EngineHookResult.CALL_NEXT


async def configure_engine_hooks(hooks: EngineHooks) -> EngineHooks:
    """p.Server(configure_hooks=...) 回调：把观测 hook 挂到官方 EngineHooks。

    在 p.Server `__aenter__` 装配期被调用（sdk.py:5695），彼时 registry 尚未初始化；
    hook 实际执行在会话处理时（lazy get_runtime()，彼时已就绪）。
    """
    hooks.on_preparation_iteration_end.append(_journey_progress_log)
    return hooks
