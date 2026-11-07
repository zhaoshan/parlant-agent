"""litellm OpenTelemetry 回调 —— **弃用（默认不装配）**，原因见下。

2026-09-28 实测（litellm 1.102）：`OpenTelemetry(tracer_provider=...)` 集成在 async
`acompletion` 下**于 span 结束后仍调用 set_attribute/set_status**，导致：
- stdout 大量 "Setting attribute on ended span." 刷屏；
- 属性（completion/usage）被 OTel SDK 丢弃，langfuse generation 数据不完整。

因此 gen_ai.* 观测改走 **patches 模块的 `install_litellm_patches()`**（monkey-patch
`LiteLLMSchematicGenerator.do_generate`，用 parlant tracer 开 span——parlant 自管 span
生命周期，无上述问题，且与 process span 嵌套天然正确），见 `app/patches/`。

若未来 litellm 修复该问题，可恢复本模块：`install_litellm_otel()` 把
`OpenTelemetry(tracer_provider=trace.get_tracer_provider())` 挂到 `litellm.callbacks`。
"""

import litellm
from litellm.integrations.opentelemetry import OpenTelemetry
from opentelemetry import trace

_installed = False


def install_litellm_otel() -> None:
    """（弃用入口）把 litellm OTel 回调挂到全局 callbacks（幂等）。当前不建议调用。"""
    global _installed
    if _installed:
        return

    callbacks = litellm.callbacks
    if not isinstance(callbacks, list):
        callbacks = []
    if any(isinstance(cb, OpenTelemetry) for cb in callbacks):
        return

    try:
        otel = OpenTelemetry(tracer_provider=trace.get_tracer_provider())
    except Exception:  # noqa: BLE001 无 provider 时降级
        return
    litellm.callbacks = [*callbacks, otel]
    _installed = True
