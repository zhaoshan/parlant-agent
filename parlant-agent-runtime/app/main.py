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
from app.extensions.observability.hooks import configure_engine_hooks
from app.routers.app_setup import configure_api
from app.services import get_runtime, init_runtime
from app.core import load_definition
from app.patches.atomic_json_file import install_atomic_json_file_write
from app.patches.do_generate import install_litellm_patches
from app.patches.eval_model_split import install_eval_model_split
from app.patches.journey_hash_stable import install_stable_journey_hash
from app.extensions.observability.langfuse_otel import configure_langfuse_otel


def install_runtime_patches() -> None:
    """统一安装全部 runtime → parlant SDK 补丁（A 类，app/patches/，全部幂等）。

    唯一安装入口：**各包 `__init__.py` 不放安装逻辑**，新增 patch 时在此登记。
    须在 p.Server 装配前完成——类级 monkey-patch 需在 SDK 注册循环等初始化
    路径执行前生效；do_generate patch 同理（装配期只构造生成器、不触发生成）。
    """
    install_atomic_json_file_write()  # 评估缓存原子写（根治 kill -9 截断）
    install_stable_journey_hash()     # 旅程评估稳定哈希（跨重启命中缓存）
    install_eval_model_split()        # 评估/对话模型分流（EVAL_LITELLM_*）+ 模型护栏
    install_litellm_patches()         # DeepSeek 关 reasoning（按 provider 路由）+ gen_ai span


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
        # 带 X-Internal-Token（doc09 §4.4 服务间信任）：server 侧 /api/internal/* 校验。
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


async def _load_published_agents_after_ready(server: p.Server) -> None:
    """启动后待 HTTP ready 再**后台**加载 published agents，评估不阻塞启动。

    背景（2026-10-21）：启动预加载会让 `__aexit__` 的 `_process_evaluations` 在
    `async with p.Server` 块体结束后全量评估已注册旅程（SiliconFlow 实测 10-24 分钟），
    启动被拖死；且 SDK/loader 双路径重复评估。改为：块体内**不加载**（评估表空 →
    __aexit__ 秒回 → Server 即时 ready）→ 等 `server.ready()` 后再后台加载；
    旅程评估走 loader 缓存路径（命中即秒回，miss 慢评不阻塞任何人）。
    首个请求若早于后台加载完成，由 server 侧 `_ensure_published_instance` 按需补加载。
    """
    try:
        await server.ready.wait()  # server.ready 是 property → Event；.wait() 是协程
    except Exception as exc:  # noqa: BLE001 - 等不到 ready 就放弃后台加载
        print(f"⚠️ 等待 server ready 失败，跳过后台加载：{type(exc).__name__}: {exc}")
        return
    try:
        loaded = await _load_published_agents()
        print(f"✅ 后台加载 published agents 完成：{loaded}")
    except Exception as exc:  # noqa: BLE001 - 后台加载失败不阻断已就绪的服务
        print(f"⚠️ 后台加载 published agents 失败：{type(exc).__name__}: {exc}")


async def main() -> None:
    settings = get_settings()
    # 全部 SDK 补丁的统一安装入口（app/patches/，幂等；须在 p.Server 装配前完成）。
    install_runtime_patches()
    # 在 p.Server 进入前派生 OTEL_* → Parlant 的 OpenTelemetryTracer 由此导出到 langfuse。
    configure_langfuse_otel(settings)

    # 阶段5 §5.7 会话状态外置：session/customer/context_variable 从本地 json 切**共享 Mongo**。
    # p.Server 的 store 支持 mongo 连接串（sdk.py make_persistable_store → MongoDocumentDatabase，
    # 各 store 独立库 parlant_sessions / parlant_customers / parlant_context_variables）；
    # 多 pod 指向同一 Mongo 即可任一 pod 接管任一会话（可水平扩展 / 故障转移的基础）。
    # ⚠️ 启用前已存在的 parlant-data/sessions.json 历史会话无法找回，启用后新建的持续可恢复。
    store_uri = settings.session_store_uri or settings.mongo_uri

    async with p.Server(
        host=settings.host,
        port=settings.port,
        nlp_service=p.NLPServices.litellm,  # 官方 OpenAI 可换成 p.NLPServices.openai
        configure_api=configure_api,
        configure_container=build_container,
        # 观测 hooks：journey.progress / process 根 span I/O（替代 parlant 源码插桩，
        # 见 app/observability/hooks）。configure_hooks 在 __aenter__ 装配期被调用。
        configure_hooks=configure_engine_hooks,
        session_store=store_uri,
        customer_store=store_uri,
        variable_store=store_uri,
    ) as server:
        # 阶段3.2：装配 runtime（registry）。
        # ⚠️ 启动**不预加载** agent：块体内零实体 → `__aexit__` 的 `_process_evaluations`
        #    遍历空评估表秒回 → Server 即时 ready；published agents 由下方后台任务在
        #    HTTP ready 后加载（评估走 loader 缓存路径）。首请求早于后台加载完成时，
        #    server 侧 `_ensure_published_instance` 会按需补加载（幂等）。
        await init_runtime(server)
        # 观测 hooks 与 SDK 补丁已在装配前统一安装（install_runtime_patches）；
        # configure_hooks 在 __aenter__ 装配期由 p.Server 调用。
        asyncio.create_task(_load_published_agents_after_ready(server))
        print("✅ parlant-agent-runtime 已装配（零预加载），Server ready 后后台加载 agents")


if __name__ == "__main__":
    asyncio.run(main())
