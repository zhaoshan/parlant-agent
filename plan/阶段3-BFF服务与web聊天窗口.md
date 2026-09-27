# 阶段3：parlant-agent-server（BFF）+ 聊天问答窗口

> 目标：建成 **web → server → runtime** 完整链路——`parlant-agent-server` 作为前端唯一入口（BFF/元数据服务），代理会话与问答（REST + SSE 透传）；`parlant-agent-web` 实现聊天前端：选定 Agent、传入客户实体信息、发起多轮问答。
> 对应参考文档：`docs/03-production/05-官方前端参考.md`、`docs/02-concepts/01-会话Session.md`、`docs/02-concepts/03-客户实体Customer.md`
> **2026-09-22 调整**：原阶段3只做 web 聊天直连 runtime；架构调整后 web **不直连 runtime**，全部经 server 代理。server BFF 骨架与代理能力并入本阶段。

---

## 交付物

### parlant-agent-server（BFF，前半阶段）
- 独立 FastAPI 工程与分包骨架（非 p.Server）：`config / models / databases / services / boundary / routers / utils`
- **runtime client**（boundary 层，httpx 异步）：load/unload agent、会话 CRUD 转发、事件 SSE 透传
- 对外 REST：`/api/agents/*`（定义 CRUD/版本/发布编排——定义层从此由 server 独占写）、`/api/sessions/*`（会话代理）
- 从 runtime 接管 DefinitionStore（Mongo `agent_definitions`），runtime 侧定义存储降级为"被动接收 + 启动拉取"
- **用户会话台账**（MySQL `user_sessions`，3.4）：按用户查会话详情，为阶段5 身份/权限打下连接与仓储基础

### parlant-agent-web（AgentStudio 工作台，后半阶段，v3.2 架构）
- **产品形态**：统一 **AgentStudio**，浅色平铺侧栏——`Agent 构建 / 模拟对话 / 追踪与观测 / 设置`（首页=点品牌），全部作用于当前 Agent
- Agent 首页（onboarding）：Agent 卡片 + 搜索 + 创建；点卡片进入 Agent 构建
- Agent 构建：构建工作台（侧栏"当前 Agent"下拉切换 + 发布确认弹窗 + 版本历史入口；组件导航带 Parlant 术语）
- 模拟对话（预览窗口）：Agent 选择 + 客户信息录入 + SSE 流式聊天（status/tool 卡片、会话边栏/执行详情可折叠）
- 消息级/轮次级 `trace_id` 展示与 langfuse 跳转（**每轮可追溯**）
- 追踪与观测：会话记录分页 + 链路浏览
- **自动仿真：设计稿先行（design/agentstudio/06），实现归并阶段6**（见 plan/阶段6）

---

## 任务清单（server BFF）

### 3.1 工程骨架与分包（✅ 2026-09-22 完成并启动验证）

> 状态：`parlant-agent-server` 已按下列分包落地并独立启动（8081）。lifespan 装配
> 连接层（MongoConnection + MySqlConnection）→ 仓储层（AgentDefinitionRepository +
> UserSessionRepository，建索引/表）→ RuntimeClient，挂到 app.state；`/health` 真实探活
> runtime（GET /health）、Mongo（ping）、MySQL（ping）；CORS 放开便于前端联调。
> 定义层存储已从 runtime 迁入并改名 `agent_definition_store.py`→仓储
> `agent_definition_repository.py`，直接读通 runtime 此前写入的同一 collection。
> RuntimeClient 按目标契约写了 load/unload/list_loaded/health——runtime 侧 load/unload
> 端点待 3.2 补齐（见任务清单注释）。

```
parlant-agent-server/
  app/
    main.py              # 独立 FastAPI 启动（uvicorn，非 p.Server）；端口 8081（8080 常被本机 Docker 占用）
    config/              # Settings（RUNTIME_BASE_URL、MONGO_URI、MYSQL_URI、CORS…）
    models/              # 对外 API DTO（定义读写、发布、会话请求/响应）
    databases/           # 【连接管理】MongoConnection / MySqlConnection（只出句柄）
    repository/          # 【仓储层】agent_definition_repository / user_session_repository（注入连接句柄）
    services/            # Agent 元数据服务（CRUD/版本/发布编排）、会话代理服务
    boundary/            # RuntimeClient（httpx 异步 + SSE 透传）、鉴权/CORS 中间件
    routers/             # /api/agents/*、/api/sessions/*、/health
    utils/               # observability、日志
  pyproject.toml
```

### 3.2 定义层迁移与发布编排（✅ 2026-09-22 完成并端到端验证）
- DefinitionStore 从 runtime `databases/` 迁入 server；mongo 集合与文档结构不变。
- **发布链路**：`POST /api/agents/{id}/publish` → server 从 Mongo 取目标版本定义 → 调 runtime `POST /internal/agents/{id}/load` 推送定义 → 成功后更新状态（published，旧版本置 archived）；runtime 加载失败返回 500 且不切换状态。
- **runtime 侧配合**：新增 `POST /internal/agents/{id}/load`（接收完整定义 JSON，幂等热加载）与 `/unload`；原定义 CRUD/publish/rollback 端点下线（定义层写已归 server）。runtime 启动时改为经 `GET server /api/internal/published-agents` 拉取 published 定义加载。
- 回滚：`POST /api/agents/{id}/rollback` 同理推送历史版本。
- **schema 共享**：server 当前只做轻量结构校验，深度校验透传 runtime 422；`agent-definition.json` 的 pydantic 模型抽共享包（server/runtime/web 三方共用）留待阶段4 前落地。

> 状态与验证记录：
> - runtime `databases/agent_definition_store.py` 已停用（runtime.py 不再引用），待后续清理删除。
> - 端到端验证通过：runtime 启动从 server 拉取 published 定义加载（server 不可达降级本地示例内存加载）；
>   `POST /api/agents/{id}/publish` 推 v2.0.0 → 1.0.0 置 archived、2.0.0 published、runtime 热加载；
>   `rollback` 回 1.0.0 → 2.0.0 置 archived、1.0.0 published、runtime 重新加载；回滚后会话正常应答。
> - 失败路径：非法定义经 server 发布 → runtime 422 透传，状态保持 draft、不加载。
> - 排障：旧 runtime 进程（17:01 启动，恰逢 internal_api.py 被改写）出现"HTTP 能看到客户、
>   引擎 read_customer 报 ItemNotFound"的 store 不一致（parlant.log 有 traceback）；独立进程容器级
>   诊断证明 container[CustomerStore]/EntityQueries/Engine 解析为同一实例，架构无 store 分裂；
>   干净重启后消失。附：Parlant 事件 DTO 中 source/kind 在顶层、data 内才是 message/status，
>   解析 SSE 勿从 data 里取 kind。

### 3.3 runtime client 与会话代理（✅ 2026-09-22 完成并端到端验证）
- `RuntimeClient`：httpx.AsyncClient 连接 `RUNTIME_BASE_URL`（默认 http://127.0.0.1:8000）；方法：`load_agent/unload_agent/list_loaded/health` + 3.3 新增 `create_session/get_session/list_sessions/create_customer/list_customers/post_event/stream_events`。
- **会话代理**：`POST /api/sessions`、`POST /api/sessions/{id}/events` 等转发到 runtime Parlant REST；响应原样返回。
- **SSE 透传**：`GET /api/sessions/{id}/events`（EventSource）→ server 用 streaming 请求订阅 runtime 事件流（`GET /sessions/{id}/events?sse=true&min_offset=&wait_for_data=`），逐帧转发给 web；断线时按 `offset` 续传。
- **MySQL 台账闭环（3.4）**：`POST /api/sessions` 成功后在 `user_sessions` 落一行；发消息时 `touch`（updated_at/last_message_at）。
- `GET /api/sessions?user_id=`（读台账列表）、`GET /api/sessions/{id}`（runtime 详情+台账合并）、`POST/GET /api/customers`（代理）。

> 状态与验证记录（全部经 8081 代理验证，未直连 runtime）：
> - 建客户（metadata 透传）→ 建会话（runtime 返回 id + MySQL 台账行 user_id/session_id/agent_id/title）→ 发消息 → SSE 透传收到 9 帧（customer echo + acknowledged/typing/processing/ready + ai_agent 回复）。
> - `GET /api/sessions?user_id=` 台账可查；`GET /api/sessions/{id}` 合并 runtime+台账。
> - 错误透传：不存在会话发消息 → runtime 404 原样映射。
> - 坑：`last_message_at` 曾用 `datetime.now()`（本地时区）与 created_at（UTC）不一致，已改 `datetime.now(timezone.utc)` 统一 UTC。
> - 参考文档：docs/03-production/08-内置ChatUI与HTTP接口分析.md（/chat 交互逻辑 + 框架 REST 清单）。

### 3.4 用户会话台账（MySQL，✅ 闭环完成 2026-09-23 v2：渠道 + 生命周期）
> 诉求（2026-09-22）：**能在 MySQL 里按用户查到会话详情**。
- 定位：Parlant 会话是引擎级事件源（事实源在 runtime）；MySQL `user_sessions` 表是
  **BFF 用户维度的可查询台账/索引**——web 端"按用户查会话列表/详情"走这里，事件流详情仍回 runtime。
- 结构：`databases/MySqlConnection` + `repository/user_session_repository`。
- **v2 扩展（2026-09-23）**：
  - `source` 来源渠道：online（线上正式问答，可多部署渠道）/ simulate（模拟对话）/ auto_sim（自动仿真）
  - `ended_at` / `ended_reason`（normal 主动关闭 / timeout 超时）：**会话生命周期在台账侧判定**，
    `valid`（active 且未结束且未超时）+ `invalid_reason`——不依赖 runtime sessions.json
  - 超时默认 1 天（`timeout_seconds` 可配），读取时计算
  - 列表 `GET /api/sessions?agent_id=&source=&user_id=&offset=&limit=`（条件可空）；`POST /{id}/close`；
    `DELETE /{id}`（台账+消息历史级联删）
- 写入时机：`POST /api/sessions` 创建时落一行（含 source）；消息时 `touch`。
- 未来扩展：阶段5 用户/登录/权限（强关系型）同样放 MySQL。

### 3.5 BFF 验收
- [x] server 独立启动（8081），`/health` 返回 runtime 健康 + mongo + mysql 状态（✅ 3.1/3.4 已验）
- [x] 经 server 发布定义 → runtime 热加载 → 新会话生效（✅ 3.2 端到端验证：发布/回滚状态流转 + 回滚后会话应答）
- [x] 经 server 创建会话/发消息/收 SSE 事件，链路完全不经前端直连 runtime（✅ 3.3 验证：建客户→建会话→发消息→SSE 透传 9 帧含 ai_agent 回复）
- [x] 在 MySQL `user_sessions` 能按 `user_id` 查到会话台账（✅ 3.4 闭环：create 落行 + touch last_message_at，`GET /api/sessions?user_id=` 可查）

---

## 任务清单（web · AgentStudio 工作台，v2 架构）

> 设计稿：`design/agentstudio/`（v3 统一产品，7 页：Agent 首页 / Agent 构建 / 旅程编辑器 / 版本历史 / 模拟对话 / 自动仿真 / 追踪与观测；admin、chat 旧稿已并入）。

### 3.6 技术栈与工程初始化（✅ 脚手架完成）
- Vite + React 18 + TypeScript + Tailwind v4（`@tailwindcss/vite`）+ zustand + react-router。
- **AgentStudio 平铺路由**（不分组，全部作用于当前 Agent）：`/`（Agent 首页 onboarding：卡片+搜索+创建，**无侧栏**）、
  `/agents/:id/build`（Agent 构建，**切换 Agent 走左侧"当前 Agent"下拉** + 发布确认弹窗）、`/agents/:id/versions`（版本历史）、
  `/simulate`（模拟对话）、`/obs`（追踪与观测，会话记录分页）。**自动仿真 `/auto-sim` 留待阶段6**。
- **浅色侧栏**：`#FFFFFF` + 发丝线，与工作区同色系（消除深/亮割裂感）；品牌=首页入口。
- vite dev 代理 `/api → 8081`；监听 `localhost:5173`（IPv6 回环，浏览器访问 localhost）。

### 3.7 新对话与客户信息传入（经 server API）（✅ 模拟对话内"新对话"对话框）
- 模拟对话页「新对话」对话框：选 Agent → 填客户身份（customer_id/name/业务字段），或内置 `guest` 冒烟。
- 流程：`POST /api/customers`（真实客户，metadata/tags/变量）→ `POST /api/sessions`（绑定 agent_id + customer_id，server 落 MySQL 台账）→ 进入聊天窗。
- 客户变量（如 `isSensitive`/`orderNum`）用于驱动旅程分支（阶段6 自动仿真重点）。

### 3.8 SSE 事件流式渲染（✅ 模拟对话已接入）
- 经 server SSE 透传端点订阅事件流，按 `offset` 增量拉取（EventSource 自动重连）。
- 模拟对话：消息气泡（来自 session_messages 历史 + SSE 实时追加）、处理中状态行、
  ai_agent 消息带 trace_id "查看链路"（阶段3.10 接 langfuse 详情）；会话边栏可收起、执行详情栏可折叠。

### 3.9 消息级历史（session_messages，✅ 已完成）——取代原"轮次 session_turns"
> 需求（2026-09-22）：**按真实消息记录**——用户提问一条、Agent 每次回复一条；
> 流式输出"首条插入、完成更新"避免频繁写库；前端生成 `request_id` 供同一次提问的用户消息 + Agent 多条回复共用。
- MySQL `session_messages`（repository/session_message_repository）：session_id / request_id / message_id
  （Parlant 事件 id，`(session_id,message_id)` 唯一 → 幂等 upsert）/ role(customer|agent) / user_id·user_name /
  agent_id·agent_name / content(Text) / content_type / **trace_id**（Agent 回复有；用户提问通常无 → 留空）/
  status(streaming|completed) / event_offset / 时间戳。
- 写入：`POST /api/sessions/{id}/events`（query 传 `request_id/user_id/user_name`，注入事件 metadata 留存 runtime）
  落客户消息；SSE 透传旁路解析 `data:` 帧，ai_agent 消息幂等 upsert（含 trace_id、chunks 流式状态）。
- 查询：`GET /api/sessions/{id}/messages?request_id=`。
- 每轮 langfuse 链路（原 3.9 目标）改由 session_messages 按 request_id 分组提供。
- 坑：中文用户名走 HTTP header 会 latin-1 乱码 → 用 **query 参数**（URL 编码 UTF-8）。

### 3.10 追踪与观测（会话记录 + 链路浏览，合并，✅ 会话记录实现）
- `/obs` 页两页签：**会话记录**（`GET /api/sessions` 分页查询，按来源筛选，点开 → **只读对话视图**，
  参考模拟对话窗口但**无输入框**，每轮消息带 langfuse 链路）；**链路浏览**（v1 跳 langfuse，可后续内嵌面板）。
- 模拟对话页的会话边栏承担"切换会话"；会话列表按当前 Agent + source=simulate，支持删除（✕）。
- **链路浏览最小可用（2026-09-24）**：支持 `/obs?trace=<trace_id>&session=<session_id>`——从模拟对话/观测只读视图点「查看链路」**跳转到本页的链路浏览 tab**（不直接跳 langfuse），展示该 trace 的轮次（用户提问 + Agent 回复，按 session_messages 同 trace_id 反查）与时间戳；langfuse 深链降级为次要入口。
- **完整 trace 树 / 工具调用 span 渲染（内嵌 langfuse 面板或自研 trace 视图）→ 挪阶段5**（含工具调用过程展示，见阶段3 §交付物说明）。

### 3.11 自动仿真（**已归并阶段6**，本阶段仅留设计稿）
- 自动仿真（仿真脚本 + 执行记录，含客户级 Variables 覆盖机制）整体移入 **`plan/阶段6-自动仿真与对话测试.md`**。
- 本阶段交付：设计稿 `design/agentstudio/06-auto-simulation.html`（去掉 AgentId 配置，作用域=当前 Agent）+ 本文档 §1 的机制说明（docs/03-production/09）。
- web 侧 `/auto-sim` 路由留占位，阶段6 实现。

### 3.12 草稿试跑 + 会话 Agent 版本隔离（✅ 2026-09-23 实现）
- **能力**：保存草稿即可试跑（校验未发布变更是否生效），**不影响线上**。
- 机制：草稿用后缀 id `{agent_id}@draft` 独立实例加载进 runtime（registry.load 按 definition.agent.id 建实体），
  试跑会话绑定它；`user_sessions` 增 `agent_instance_id / agent_version / agent_status`（草稿="draft"）。
- `POST /api/sessions` 支持 `mode: draft|published`；server 取最新 draft 定义→后缀 id 幂等加载→建会话绑实例→落台账；
  **草稿会话关闭/删除后无剩余活跃时立即卸载 @draft 实例**。
- **发布策略**：阶段3 接受 Parlant 原生（发布=热加载覆盖，线上进行中会话切新版本，无会话级版本快照）；
  **阶段5 增强**：published 也用版本实例 + 会话创建时版本快照，发布加载新实例、旧实例服务旧会话直至自然结束。
- 设计文档：`docs/03-production/10-草稿试跑与会话版本隔离.md`；前端模拟对话「新对话」含 草稿/线上 二选一 + 列表草稿徽标。

---

## 依赖组件

| 组件 | 用途 |
|---|---|
| parlant-agent-runtime（阶段2 `/internal/*`） | server 的下游：加载/问答 |
| parlant-agent-server（本阶段前半） | web 的唯一后端 |
| MongoDB | 定义层（agent_definitions） |
| MySQL | 用户会话台账 user_sessions（3.4）+ 轮次 session_turns（3.9）；仿真 sim_configs·sim_runs 归阶段6 |
| langfuse | trace 跳转目标（每轮 trace_id 关联） |
| 浏览器 EventSource/fetch-stream | SSE 消费 |

---

## 验收标准

- [ ] server 独立运行，web 全部数据经 server（无直连 runtime）
- [ ] 选不同 Agent + 不同 customer 信息，得到不同业务回复
- [ ] customer 变量（如 `isSensitive=true`）能改变旅程走向（命中"敏感身份"分支）
- [ ] 流式展示消息与"工具调用"过程
- [ ] 从会话记录的**每一轮**点击"查看链路"，在 langfuse 看到该轮完整 span 树（session_turns 落库）
- [ ] 在 server 上发布/回滚定义，runtime 热加载生效（无需重启 runtime）
- [ ] 在 MySQL `user_sessions`（及 `session_turns`）能按 `user_id` 查到会话与轮次详情

---

## 风险与提示

- **SSE 透传断连**：server 到 runtime、web 到 server 两段长连接各自独立重连，注意 offset 续传与事件顺序，必要时以服务端 offset 为准重排。
- **发布一致性**：server 推送 runtime 加载失败时要保持定义层状态不变（未 published），并给前端明确报错。
- **offset 断点**：刷新/断线重连时用本地最后 `offset` 续传，避免丢消息。
- **TOOL 展示粒度**：工具结果可能含敏感数据，前端展示前考虑脱敏规则。
