# 阶段2：Agent 定义转换与多 Agent 调度（runtime 内部能力，体系枢纽）

> 目标：把阶段1的手动映射升级为**通用加载器**——`agent-definition.json` 自动转换为 Parlant 实体；建立 **Agent 注册表**支持多 Agent 动态加载、版本化与热更新；为上游 BFF 提供 runtime 内部 API。
> 对应学习资料：`docs/02-concepts/*`（逐组件）、`docs/04-execution-chain/02-核心模块源码地图.md`
> **2026-09-22 调整**：承载项目更名为 `parlant-agent-runtime`；原任务 2.5「管理 API（供 admin）」改为 **runtime `/internal/*` API**（只面向 parlant-agent-server，不面向前端）。定义层 MongoDB 本阶段暂存于 runtime（`databases/`），阶段3 建 server 时迁移（server 独占写、runtime 被动接收推送 + 启动拉取）。

---

## 交付物

- `agent-definition.json` 的正式 pydantic Schema + 校验器（`models/definition.py`）
- `DefinitionStore`（MongoDB 存定义，含版本与状态；本阶段位于 runtime `databases/`，阶段3 迁移至 server）
- `AgentLoader`（定义 → Parlant 实体的通用转换器，`services/`）
- `AgentRegistry`（多 Agent 管理：注册/激活/停用/热更新/回滚，`services/`）
- 一组 runtime 内部 API（`configure_api` 扩展，`/internal/*`，供阶段3 的 parlant-agent-server 调用）
- Parlant 实体存储切换到 MongoDB

---

## 任务清单

### 2.1 定义层 Schema 化
- 依据 `agent-definition.json` 提炼 pydantic 模型：顶层 `agent / guidelines / journeys / variables / glossary / canned_responses / tools / retrievers / relationships / observations`。
- 每个组件字段对齐 Parlant 实体属性（见源码地图）。给出清晰报错。
- 处理样本中的空/可空字段（`relationships/observations/experience_criteria` 等允许为空）。

### 2.2 DefinitionStore（MongoDB）
- collection `agent_definitions`：`{ agent_id, version, status(draft|published|archived), definition, created_at, updated_at, created_by }`。
- 支持多版本并存；`published` 为当前线上版本。
- **归属说明**：架构调整后定义层由 parlant-agent-server 独占写；本阶段作为 runtime 内部存储先行落地，接口设计向"未来由 server 推送定义"对齐（save/set_status 作为内部能力保留，对外只暴露 load/unload）。

### 2.3 AgentLoader（核心转换器）
`definition.json → parlant 实体` 的映射规则：

| definition 字段 | Parlant 实体 | 备注 |
|---|---|---|
| `agent` | Agent | description/utterances/boundary/composition_mode |
| `guidelines[]` | Guideline | condition/action/criticality/priority；`journey_ids`/`tools`/`retrievers`/`variable_conditions`/`variable_updates_on_match` 建立关联 |
| `journeys[]` | Journey | `entry_node` + `states[]`(chat/tool/fork) + `transitions[]`(condition/variable_conditions) |
| `variables[]` | ContextVariable | type/default_value/freshness_rules |
| `glossary[]` | Term | name/synonyms/description |
| `canned_responses[]` | CannedResponse | template/usage_context/bound_to |
| `tools[]` | Tool | builtin 直接启用；自定义用 `@p.tool`；外部用 OpenAPI/MCP |
| `retrievers[]` | Retriever | `ragflow_http` 需 endpoint/collection；或接 Qdrant |
| `relationships[]` | Relationship | 蕴含/优先级/依赖/消歧 |

- **关键**：转换要幂等（重复加载同版本不重复建实体）；支持"先建到暂存再切换生效"。

### 2.4 AgentRegistry（多 Agent 动态调度）
- 维护 `agent_id → 已加载 parlant agent` 映射。
- 运行时加载：新 agent 经 loader 转换后注册进 `p.Server()`，**无需重启**。
- 版本切换：publish 新版本 → 热更新实体；支持回滚到历史版本。
- 全局资源（共享工具/检索器/向量库连接）注册一次，各 agent 引用。

### 2.5 runtime 内部 API（configure_api 扩展，`/internal/*`）
> 原"管理 API（供阶段4 admin）"调整为本节。只面向 parlant-agent-server（BFF），Parlant REST/SSE 端口仅绑内网（127.0.0.1 或内网地址）。
```
GET    /internal/agents                 # runtime 已加载 agent 列表 + 加载状态
POST   /internal/agents/{id}/load       # 接收完整定义 JSON，热加载进引擎（幂等）
POST   /internal/agents/{id}/unload     # 卸载引擎实体
GET    /internal/health                 # 引擎健康（供 server 探活/选主）
```
- 全部走 `configure_api` 挂在 Parlant app 上（见 `docs/03-production/07-FastAPI扩展.md`）。
- **阶段3 衔接**：server 建好后，Agent 定义 CRUD/版本/发布编排迁到 server（`/api/agents/*`），发布时 server 调本节的 `load` 推送定义；runtime 启动时向 server 拉取 published 定义。届时本节保留 load/unload/health，定义存储的写操作下线。

### 2.6 切换到 MongoDB
- `configure_container` 注入 MongoDB 文档库，替换默认本地存储（见 `docs/concepts/sessions.md`、`docs/adapters/persistence/*`）。

### 2.7 工具与检索器落地
- 内置工具（`journey_node_counter`/`variable_update`/`tavily_search`）按定义启用。
- 自定义业务工具用 `@p.tool` 实现（如"查合同""办预约"）。
- 检索器：`ragflow_http` 配 endpoint/collection；或接 Qdrant 向量库；`top_k`/`min_score` 按定义生效（见 `docs/02-concepts/06-检索器Retrievers.md`）。

---

## 依赖组件

| 组件 | 用途 |
|---|---|
| MongoDB | 定义层 + Parlant 实体存储 |
| Qdrant / RAGFlow | 检索器（用到时） |
| 阶段1 服务 | 在其上扩展 loader/registry |

---

## 验收标准（2026-09-22，除标注外全部通过）

- [x] 上传一份新 `agent-definition.json` → 无需重启即可与之对话（经 `/internal/agents/{id}/load` 热加载）——实测新建 `onb-second-test`：upsert → publish → 对话正常
- [x] 同库可并存 ≥2 个 Agent，会话按 `agent_id` 隔离——实测两 agent 各 7 条指南独立，会话绑定各自的 agent
- [x] 修改指南后 publish，新会话立即生效；可 rollback——publish/rollback 端点全通
- [ ] 旅程变量（`isEligible`/`orderNum`...）在会话中正确读写——**未验**（当前分支走向由工具结果驱动）
- [ ] 检索器命中知识库时，回复引用检索内容（langfuse 可见 `tool_caller`）——**未实现**（ragflow/qdrant 接入推迟）
- [x] runtime `/internal/*` API 可用：load 幂等（重复加载不产生重复实体）、unload 干净卸载——实测连发 3 次 publish 指南数稳定 7，unload 后归 0

---

## 风险与提示

- **幂等与一致性**：转换失败要整体回滚，避免"建了一半"的 agent。建议 loader 内部用事务/补偿。
- **热更新边界**：运行中会话的 `journey_paths` 已持久化，改旅程定义可能影响在途会话——发布时考虑只影响新会话。
- **多 Agent 资源隔离**：共享向量库时，用 collection/metadata_filter 按 agent 隔离知识。
