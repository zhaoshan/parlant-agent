# 阶段0：环境与基础

> 目标：把基础设施和依赖全部备齐，跑通官方 quickstart 示例，为后续开发扫清环境障碍。
> 对应学习资料：`docs/01-quickstart/01-安装.md`、`docs/01-quickstart/02-快速入门示例.md`

---

## 交付物

- 可用的 Python 环境（parlant 已装）
- LLM / Embedder 接入可用
- langfuse、MongoDB、Qdrant 三个 docker 服务运行中
- 官方 quickstart 示例 agent 能对话
- langfuse 中能看到该示例的 trace

---

## 任务清单

### 0.1 安装 Parlant（当前 `.venv` 尚未安装）
```bash
cd /Users/zhaoshan/workspace/parlant-study
source .venv/bin/activate
pip install parlant
python -c "import parlant; print(parlant.__version__)"   # 期望 3.3.x
```
> 也可 `pip install -e /Users/zhaoshan/workspace/parlant` 以可编辑方式装本地源码，便于后续加日志调试执行链路。

### 0.2 配置 LLM / Embedder
- 准备 OpenAI 兼容的 Key（或 Azure/Vertex/Ollama/OpenRouter，见 `docs/advanced/custom-llms.md` 与 `docs/adapters/nlp/*`）。
- 用环境变量注入（具体变量名以所用 NLP 适配器为准）。
- 验证：跑一次最小 `p.Server()` 对话，确认 LLM 与 embedder 均通。

### 0.3 起 langfuse（docker 自托管 或 Cloud）
- docker compose 起 langfuse，拿到 OTLP endpoint。
- 记录 `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` 待用（阶段1注入）。

### 0.4 起 MongoDB（docker）
- 生产级实体/会话存储。开发期可先用 Parlant 默认本地文档库，但建议早早在 docker 里备好。
- 参考 `docs/concepts/sessions.md`（会话存储配置）与 `docs/adapters/persistence/*`。

### 0.5 起 Qdrant（docker）
- 检索器向量库（阶段2/4 用到 `ragflow_http`/Qdrant 检索器时必需）。
- 参考 `docs/adapters/vector_db/qdrant.md`。

### 0.6 跑通官方 quickstart
- 按 `docs/01-quickstart/02-快速入门示例.md` 逐步创建 agent + guideline + journey + tool，发起一次对话。
- **此步是理解"上下文工程组件如何组装"的第一手实践**，建议边做边对照 `docs/02-concepts/*`。

---

## 依赖组件

| 组件 | 状态要求 |
|---|---|
| Python 3.11+ / .venv | 已有 venv，装 parlant 即可 |
| LLM + Embedder Key | 必需 |
| docker / docker compose | 起 langfuse/mongo/qdrant |
| langfuse | 阶段1起用，先备好 |

---

## 验收标准

- [x] `python -c "import parlant"` 成功（本地源码 editable 安装，`parlant[litellm]` 的 torch 依赖以惰性导入补丁绕过，见 parlant-agent-server/pyproject.toml 注释）
- [x] 官方示例 agent 能完成一次多轮对话（含指南命中）——`examples/healthcare_demo.py`：旅程推进 + `get_upcoming_slots` 工具调用 + 术语（Dr. Xavier）
- [x] langfuse UI 能检索到这次对话的 trace（含 `process`/`message_generation` span）——trace `ee8611ef…` 完整含 process → preparation_iteration → guideline_matcher/relational_resolver/tool_caller/message_generation/response_analysis

---

## 风险与提示

- **LLM 选型**：若走 Ollama 本地，注意指南匹配等内部多次 LLM 调用对本地模型延迟敏感；学习期建议用云端模型。
- **embedder 不可少**：术语匹配/检索都依赖 embedding，别只配了 chat 模型。
- **网络**：确认本机到 docker 容器（mongo/qdrant/langfuse）端口可达。
