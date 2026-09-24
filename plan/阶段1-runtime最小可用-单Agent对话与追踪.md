# 阶段1：parlant-agent-runtime 最小可用（单 Agent + 追踪）

> 目标：用 FastAPI 包装 `p.Server()` 起服务，加载示例"提前结清"Agent，完成一次带 langfuse 追踪的问答。
> 对应学习资料：`docs/03-production/07-FastAPI扩展.md`、`docs/03-production/04-API增强.md`、`docs/03-production/06-可观测性.md`、`docs/04-execution-chain/*`
> **2026-09-22 调整**：本项目原名为 `parlant-agent-server`，架构调整后更名为 **`parlant-agent-runtime`**（执行引擎服务）；新的 `parlant-agent-server` 是阶段3才建的 BFF/元数据服务。

---

## 交付物

- `parlant-agent-runtime` 项目骨架（可 `uvicorn`/脚本启动）
- `p.Server(configure_api=..., configure_container=...)` 包装服务
- 示例"提前结清"Agent 已加载并能对话
- OTEL 注入，langfuse 可见完整执行链路 span

---

## 任务清单

### 1.1 项目骨架（按 2026-09-22 调整后的分包结构）
```
parlant-agent-runtime/
  app/
    main.py              # 入口：p.Server 装配与启动
    config/              # Settings（env：LLM/OTEL/MONGO/QDRANT/端口…）
    models/              # 定义层 pydantic schema（阶段2.1 的 definition.py）
    databases/           # Mongo 存储（阶段2.2 的 DefinitionStore）
    services/            # AgentLoader / AgentRegistry / runtime 装配 / 内置工具 / 示例 bootstrap
    routers/             # configure_api 挂载：/health + /internal/*（阶段2.5）
    boundary/            # 防腐层：Parlant 引擎装配（policies/容器配置）
    utils/               # observability（langfuse OTEL/FastAPI 仪器化）等
  pyproject.toml
```

### 1.2 最小 Server 入口
```python
import parlant.sdk as p

async def configure_api(app):
    @app.get("/health")
    async def health(): return {"status": "ok"}

async with p.Server(configure_api=configure_api) as server:
    ...  # 退出 async with 块时 __aexit__ 启动 HTTP 服务并阻塞（v3.3.1 无 serve()）
```
- 用 `configure_container` 注册开发用 `p.DevelopmentAuthorizationPolicy`（允许跨域，便于前端联调）。
- CORS 通过重写 policy 的 `configure_app` 配置（见 `docs/03-production/04-API增强.md`）。

### 1.3 装载示例 Agent（手动映射，阶段2再自动化）
- 读 `agent-definition.json`，用 Parlant SDK 创建对应实体（具体调用对照 `docs/01-quickstart/02-快速入门示例.md`）：
  - `agent` → Agent（含 description/utterances/boundary）
  - `guidelines[]` → Guideline（condition/action/criticality/priority/journey_ids）
  - `journeys[]` → Journey（entry_node/states/transitions）
  - `variables[]` → ContextVariable（含 default_value/freshness_rules）
  - `glossary[]` → Term；`canned_responses[]` → CannedResponse
  - `tools[]` → 内置工具直接启用；自定义工具用 `@p.tool`
- 这一步**亲手把 JSON 的每个字段映射到 parlant 实体**，是理解 schema 与引擎关系的最佳实践。

### 1.4 接可观测性
```bash
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="<langfuse-otlp>/v1/traces"
export OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"
export OTEL_SERVICE_NAME="parlant-agent-runtime"
```
- 验证 langfuse 能看到 `process` / `guideline_matcher`(phase) / `tool_caller` / `message_generation` span。
- 对照 `docs/04-execution-chain/03-可观测性与追踪对接.md`。

### 1.5 端到端验证
- `POST /sessions/{id}/events`（source=CUSTOMER）发一条消息。
- 通过事件接口/SSE 收到智能体回复。
- 取事件 `trace_id` 在 langfuse 还原处理链路。

---

## 依赖组件

| 组件 | 用途 |
|---|---|
| 阶段0 全部 | 环境已就绪 |
| LLM + Embedder | 推理 |
| langfuse | 追踪展示 |
| Parlant 默认文档库 | 阶段1先用本地存储，MongoDB 阶段2再切 |

---

## 验收标准（2026-09-22 全部通过）

- [x] `GET /health` 返回 ok
- [x] 示例"提前结清"agent 能对"你好"/"我要提前结清"给出符合指南的回复
- [x] 旅程能推进（如：识别合同→挽留→预约）——实测：触发旅程 → 列合同 → 选定 0001 → eligibility 逾期分支话术
- [x] langfuse 按 `trace_id` 可见 `guideline_matcher` 命中了哪条指南——实测：`process → guideline_matcher → tool_caller → message_generation` 全链可见

---

## 风险与提示

- **会话 mode**：若工具把 session 改为 `manual`（人工接管），引擎不再自动回复——阶段1先确保示例不触发。
- **迭代上限**：工具触发再匹配受 `max_engine_iterations` 约束，调试时留意日志中的 "Reached max tool call iterations"。
- **提示词泄漏**：LLM 被明确要求不暴露内部机制，若发现泄漏，检查是否某指南 action 写得太"指令化"。
