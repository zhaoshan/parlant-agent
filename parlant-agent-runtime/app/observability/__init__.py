"""观测与模型适配集中层（doc12 落地：parlant 源码插桩全部移出，集中到 runtime）。

子包分工：
- ``otel/``    litellm OpenTelemetry 回调（**弃用**：async 下 ended-span 刷屏，见 otel/__init__）
- ``hooks/``   EngineHooks 装配（journey.progress + process 根 span I/O）
- ``patches/`` monkey-patch（DeepSeek reasoning 注入 + gen_ai.chat span）
- ``labels/``  journey index → 节点名称（BFS 复刻 parlant 投影）

装配顺序：
1. `p.Server(configure_hooks=configure_engine_hooks)` —— hooks 在 `__aenter__` 装配期注入；
2. `install_observability()` —— 在 `async with` 块内 `init_runtime()` 之后调用（patches）。
"""

from app.observability.hooks import configure_engine_hooks
from app.observability.patches import install_litellm_patches

__all__ = ["configure_engine_hooks", "install_observability"]


def install_observability() -> None:
    """装配 patches（幂等）。在 p.Server `__aenter__` 后调用。

    gen_ai.* 观测走 patches 的 do_generate monkey-patch（parlant tracer 开 span）；
    litellm OTel 回调因 ended-span 刷屏弃用（见 app/observability/otel/）。
    """
    install_litellm_patches()
