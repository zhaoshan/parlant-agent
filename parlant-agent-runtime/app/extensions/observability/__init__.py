"""观测扩展（B 类：SDK 官方扩展点，零 parlant 源码改动，见 docs/06-dev-process/05）。

本 `__init__.py` 只承载包说明：**不放任何业务逻辑 / patch 安装**。

子模块分工：
- ``hooks``          EngineHooks 装配（journey.progress + process 根 span I/O）——
                     经 p.Server(configure_hooks=...) 官方入口注入（__aenter__ 装配期）；
                     main.py 直接 ``from app.extensions.observability.hooks import configure_engine_hooks``
- ``langfuse_otel``  env 派生 OTEL_* + FastAPI instrumentor（trace 属性钩子）
- ``litellm_otel``   litellm OpenTelemetry 回调（**弃用**：async 下 ended-span 刷屏，
                     gen_ai.* 观测走 app/patches/do_generate.py）

A 类 patch（DeepSeek reasoning 等）的安装不在本包——统一入口见
``app.main.install_runtime_patches()``。
"""
