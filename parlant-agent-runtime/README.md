# parlant-agent-runtime

**Parlant 执行引擎服务**：加载 Agent 定义，调度 Parlant AlphaEngine 执行业务逻辑（问答 / 旅程 / 工具）。

> 定位（对应 `plan/README.md` 应用划分）：本服务**不直接面向前端**，Parlant REST/SSE 端口仅绑内网；对外只暴露少量 `/internal/*` 端点。前端唯一入口是 [parlant-agent-server](../parlant-agent-server/README.md)（BFF）。

## 架构定位

- 用 `p.Server()`（Parlant v3.3.1）承载引擎，包一层 FastAPI 扩展挂 `/internal/*` + `/health`。
- **定义层由 parlant-agent-server 独占写**（MongoDB `agent_definitions`）；runtime 不再持有定义存储：
  - 启动时经 `GET {server}/api/internal/published-agents` 拉取全部 published 定义加载；server 不可达或暂无 published 时**降级用本地示例定义在内存加载**（不写库），保证开发期可启动。
  - 发布/回滚/草稿试跑由 server 推 `POST /internal/agents/{id}/load` 热加载。
- 会话/客户持久化：`p.Server(session_store="local", customer_store="local")` → `parlant-data/sessions.json`、`customers.json`（事件随会话落盘，重启可续）。
- 追踪：OTLP 直投 langfuse（`app/utils/observability.py` 由 langfuse 三件套派生 `OTEL_*`）。

## 快速启动

```bash
# 0. 依赖（uv 管理；parlant 本体走 [tool.uv.sources] 指向 ../../parlant 本地 editable 安装）
uv sync

# 1. 环境变量：复制 .env.example → .env，填 LITELLM_PROVIDER_* / MONGO_URI / QDRANT_URL
#    （LANGFUSE_* 三件套可放本目录 .env 或工作区根目录 .env，Settings 两个都读）
cp .env.example .env

# 2. 启动（先起 parlant-agent-server 8081 可加载线上 published 定义；不可达则降级示例）
.venv/bin/python -m app.main
```

服务监听 `0.0.0.0:8000`（Parlant REST/SSE，仅内网）+ `8818`（tool service）。

## 环境变量

见 `.env.example`。关键项：

| 变量 | 说明 |
|---|---|
| `LITELLM_PROVIDER_MODEL_NAME` | 对话模型，**必须带 provider 前缀**（如 `openai/xxx`），适配器不做拼接 |
| `LITELLM_PROVIDER_BASE_URL` / `LITELLM_PROVIDER_API_KEY` | OpenAI 兼容端点 |
| `LITELLM_EMBEDDING_MODEL_NAME` / `LITELLM_EMBEDDING_DIMENSIONS` | embedding 模型；**DIMENSIONS 必须等于真实维度**（transient 向量库预分配矩阵宽度，不一致 vstack 报错） |
| `MONGO_URI` / `QDRANT_URL` | MongoDB / Qdrant |
| `LANGFUSE_SECRET_KEY` / `PUBLIC_KEY` / `BASE_URL` | langfuse OTLP 追踪（启动时自动派生 OTEL_*） |
| `TAVILY_API_KEY` | 可选，示例内置工具 `tavily_search` |

## 内部 API（仅面向 parlant-agent-server）

| 端点 | 说明 |
|---|---|
| `GET  /internal/agents` | 已加载 agent 列表 + 加载状态 |
| `POST /internal/agents/{id}/load` | 接收完整定义 JSON，**幂等热加载**（已存在先卸载再重建）；兼容裸定义或 `{"definition":...}` 包裹；校验定义 agent.id 与路径一致（422）；body 带 `@draft` 后缀 id 即草稿试跑实例 |
| `POST /internal/agents/{id}/unload` | 卸载引擎实体（含子实体级联清理）；未加载 404 |
| `GET  /internal/health` | 引擎健康 |

> `configure_api` 在 `p.Server.__aenter__` 内调用、HTTP 服务在 `__aexit__` 才启动；因此端点里访问 runtime 单例**必须请求期惰性 `get_runtime()`**，不能在注册期取。

## 代码结构（app 包）

```
app/
├── main.py                  # 入口：p.Server() 装配 + 启动拉取 published 定义
├── config/settings.py       # 集中配置（读 .env：项目 .env 优先于根 .env）
├── models/
│   └── definition.py        # agent-definition.json 的 pydantic 模型 + parse_definition
├── services/
│   ├── runtime.py           # 运行期单例（server + registry，get_runtime 惰性取用）
│   ├── agent_registry.py    # Agent 注册表：load/unload/list（幂等语义在此）
│   ├── agent_loader.py      # 定义 → Parlant 实体装配器（指南/旅程/变量/术语/话术/工具）
│   │                        #   · 旅程/状态 id 加实例后缀隔离（@draft）
│   │                        #   · 热加载旅程**后台评估**（reachable_follow_ups 分叉条件表）
│   ├── agent_bootstrap.py   # 阶段1 示例定义加载（保留作降级路径）
│   └── builtin_tools.py     # 自研内置工具：journey_node_counter / variable_update / tavily_search
├── routers/
│   ├── internal_api.py      # /internal/*（上表）
│   └── api_extensions.py    # configure_api 挂载点
├── boundary/policies.py     # configure_container 注入（鉴权策略/容器装配）
└── utils/observability.py   # langfuse OTLP 派生 + 追踪降噪（console/HTTP 噪声采样）
```

### 关键实现点（务必了解）

- **AgentLoader 幂等**：`load()` 先查 agent_id 已存在 → 先卸载（删 agent + 打 agent 标签的全部子实体）再重建，保证「重复加载不重复建实体」「发布即生效」。
- **实例后缀隔离**（`_instance_suffix`）：定义层实体 id（`jny_*`/`sta_*`）进引擎**全局**存储——旅程 id 全局唯一（重复报 `already exists`）、状态 id 重复会静默覆盖。带 `@` 的实例（如 `{agent_id}@draft`）其旅程/状态 id 统一加后缀；published 主实例无后缀，与定义层完全对账。
- **热加载旅程必须后台补评估**（`_evaluate_journeys_now`）：分叉推进依赖节点指南上的 `journey_node.reachable_follow_ups` 条件表，它只由 SDK `__aexit__` 评估阶段产出（启动前加载的实体才有）。热加载实体（publish/rollback/@draft）等不到 → 必须逐旅程 `evaluate_journey`（内容哈希缓存于 `parlant-data/evaluation_cache.json`，未变秒回）+ `_apply_single_evaluation`。**必须后台化**（`asyncio.create_task`）：全量评估是逐节点多次 LLM 调用，实测可达数分钟，阻塞会拖死 load/会话创建。
- **内置工具契约**：`@p.tool` 的文件不能有 `from __future__ import annotations`（注解变字符串 → 装饰器断言失败）；泛型只支持 `list`（dict 注解报错，用 `str` + JSON 字符串）。`variable_update` 需 `set_runtime_services(server.container)` 注入容器才能写 ContextVariableStore。

## 运行数据

- `parlant-data/`（启动 cwd 下，相对路径！）：`sessions.json` / `customers.json`（会话持久化）、`cache_embeddings.json`（删除后首启 10–15 分钟重算 embedding）、`evaluation_cache.json`（旅程评估缓存）、`parlant.log`。`PARLANT_HOME` 默认启动 cwd 下的 `parlant-data/`，从不同 cwd 启动会产生多份数据目录。
- 该目录不入 git（见根 `.gitignore`）。

## 常用运维

- **停进程**：Parlant 对 SIGTERM 不敏感，需 `kill -9` + `lsof -iTCP:8000 -sTCP:LISTEN` 确认。
- **服务间 502 陷阱**：httpx 默认 `trust_env=True` 会读 macOS 系统代理（如 `:7899`），127.0.0.1 请求被转代理 → 目标不可达时代理回 502（健康时可透传，好时坏）。runtime↔server 所有 httpx 客户端均须 `trust_env=False` 直连。

## 样例

- `examples/healthcare_demo.py`（阶段0 demo，:8800）
- 真实样例 agent：`onb-094c4bbe2663`（提前结清；6 指南 / 1 旅程 12 状态 / 6 变量 / 1 术语 / 2 话术 / 3 工具），定义保存在 Mongo（server 定义层），经发布加载。
