"""入口：用 p.Server() 启动 Parlant，包一层 FastAPI 扩展。

运行：
    python -m app.main

阶段3（BFF 时代）启动流程：
    __aenter__ 装配容器 -> init_runtime(server)
        -> 从 server `/api/internal/published-agents` 拉取全部 published 定义加载
        -> server 不可达时降级用本地示例定义（内存，不写库）
    -> __aexit__ 启动 HTTP 服务（configure_api 挂 /internal/* + /health）。

说明（对照 v3.3.1 源码确认）：
- 入口是 `parlant.sdk`（`import parlant` 顶层是空的，没有 Server）；
- p.Server 不收 authorization_policy 参数，鉴权策略经 configure_container 注入；
- p.Server **没有 serve() 方法**：`async with p.Server()` 块内做装配，
  退出块时 __aexit__ 才真正启动 HTTP 服务并阻塞（sdk.py:4340 "This actually starts the server"）；
- NLP 服务默认 NLPServices.emcie；OpenAI 官方用 NLPServices.openai，
  OpenAI 兼容的第三方/代理用 NLPServices.litellm（LITELLM_PROVIDER_* 环境变量）；
- v3.3.1 的 OpenAI 适配器内部模型名是硬编码的（如 gpt-4o-2024-11-20），
  想自由指定模型名请走 litellm。
"""

import asyncio

import httpx
import parlant.sdk as p

from app.boundary.policies import build_container
from app.config import get_settings
from app.models import parse_definition
from app.observability import configure_engine_hooks, install_observability
from app.routers.app_setup import configure_api
from app.services import get_runtime, init_runtime
from app.services.agent_loader import load_definition
from app.utils.observability import configure_langfuse_otel


async def _load_published_agents() -> list[str]:
    """启动时从 parlant-agent-server 拉取全部 published 定义并加载。

    定义层已归 server 独占写（阶段3.2）；server 不可达或暂无 published 时，
    降级用本地示例定义在**内存**加载（不写库），保证开发期仍可启动。
    返回已加载的 agent_id 列表。
    """
    rt = get_runtime()
    settings = get_settings()
    loaded: list[str] = []

    try:
        # trust_env=False：服务间 127.0.0.1 通信必须直连——本机若开系统代理
        # （macOS 网络设置里的 HTTP 代理，httpx trust_env 默认会读），请求会被转给
        # 代理，目标不可达时代理回 502 Bad Gateway（服务健康时代理可透传 loopback，
        # 故联调时好时坏）。
        # 带 X-Internal-Token（doc16 §4.4 服务间信任）：server 侧 /api/internal/* 校验。
        headers: dict[str, str] = {}
        if settings.internal_token:
            headers["X-Internal-Token"] = settings.internal_token
        async with httpx.AsyncClient(timeout=10.0, trust_env=False, headers=headers) as client:
            resp = await client.get(f"{settings.server_base_url}/api/internal/published-agents")
            resp.raise_for_status()
            published = resp.json().get("agents", [])
    except Exception as exc:  # noqa: BLE001 - server 不可达则降级
        print(f"⚠️ 无法从 server 拉取 published 定义（{type(exc).__name__}: {exc}），"
              f"降级用本地示例定义加载")
        published = []

    if not published:
        # 降级：示例定义内存加载（不再写库）
        data = load_definition()
        definition = parse_definition(data)
        agent = await rt.registry.load(definition)
        loaded.append(agent.id)
        return loaded

    for doc in published:
        definition = parse_definition(doc["definition"])
        agent = await rt.registry.load(definition)
        loaded.append(agent.id)
    return loaded


async def main() -> None:
    settings = get_settings()
    # 在 p.Server 进入前派生 OTEL_* → Parlant 的 OpenTelemetryTracer 由此导出到 langfuse。
    configure_langfuse_otel(settings)

    async with p.Server(
        host=settings.host,
        port=settings.port,
        nlp_service=p.NLPServices.litellm,  # 官方 OpenAI 可换成 p.NLPServices.openai
        configure_api=configure_api,
        configure_container=build_container,
        # 观测 hooks：journey.progress / process 根 span I/O（替代 parlant 源码插桩，
        # 见 app/observability/hooks）。configure_hooks 在 __aenter__ 装配期被调用。
        configure_hooks=configure_engine_hooks,
        # 阶段3.3 修复：会话/客户默认 transient（重启即失，历史会话继续问答报
        # "Session not found"）。改 "local" 持久化到 parlant-data/sessions.json、
        # customers.json（事件随会话一起落盘）；agent 实体仍启动时从 Mongo 重建。
        # 注意：启用前已存在的历史会话（在旧内存态）无法找回，启用后新建的可持续。
        session_store="local",
        customer_store="local",
    ) as server:
        # 阶段3.2：装配 runtime（registry），从 server 拉取 published 定义加载。
        # 退出 async with 块时，__aexit__ 会自动启动 HTTP 服务并阻塞直至被信号中断。
        await init_runtime(server)
        # 观测/模型适配集中装配（litellm OTel 回调 + DeepSeek reasoning patch，幂等）
        install_observability()
        loaded = await _load_published_agents()
        print(f"✅ parlant-agent-runtime 已装配，加载 {len(loaded)} 个 Agent：{loaded}")


if __name__ == "__main__":
    asyncio.run(main())
