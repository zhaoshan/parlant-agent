# 内置 /chat 聊天 UI 与框架 REST 接口分析（自研源码分析）

> 自研分析（非官方文档直译），2026-09-22，依据 Parlant v3.3.1 本地源码
> `src/parlant/api/chat/src/` 与 `src/parlant/api/` 逐行核实。
> 用途：理解 Parlant 自带聊天 UI 的完整交互逻辑，作为本仓库 server BFF 阶段3.3
> 会话代理与 web 聊天前端的实现参照。

---

## 1. 一句话结论

**Parlant 内置 `/chat` 页面不做任何独立持久化，它全部通过调用框架自己的 HTTP REST 接口**
（`GET /agents`、`GET /customers`、`POST /sessions`、`POST /sessions/{id}/events`、
`GET /sessions/{id}/events`）完成 agent 选择、客户确定、会话创建、消息收发与事件流订阅。
"自动"行为只是前端在"只有一个选项"时的默认选中，不是框架替你建了什么隐藏资源。

---

## 2. Agent 选择：单/多两种形态

数据源：`GET /agents`（runtime 的 AgentStore，**只返回已加载的引擎实体**，未加载的定义不出现）。

`components/agents-list/agent-list.tsx:24-26`：

```ts
useEffect(() => {
    if (agents?.length && agents.length === 1) selectAgent(agents[0]);
}, []);
```

- **1 个 agent** → 进页面自动选中，直接可聊。
- **≥2 个 agent** → 不自动选；点左上角「New Session」按钮（`chat-header.tsx` `createNewSession`）
  弹出对话框，标题为 **"Select an Agent"**，列出全部 agent，点选切换。

### 与 server BFF 的关系
web 前端不直连 runtime。`GET /agents` 由 server 代理（阶段3.3 `/api/agents` 列表带 `loaded` 标志），
前端只展示"已加载"的 agent。

---

## 3. 客户（Customer）确定：内置 guest + 自动首项

数据源：`GET /customers`。

- **`guest` 是框架内置的特殊客户**：`core/customers.py:64` `GUEST_ID = CustomerId("guest")`，
  `api/customers.py:411` 文档明确"分页首项永远包含 `guest`"。SDK 侧 `Customer.guest` classproperty
  （`sdk.py:3211`）即 `id="guest", name="Guest"`。
- 选完 agent 后：`agent-list.tsx` `selectAgent` 内 `if (customers.length < 2) selectCustomer(customers?.[0], agent)`
  —— 当客户列表只有 `guest` 一个（`length < 2`）时**自动选 guest**；有多个客户时再弹 **"Select a Customer"** 对话框。

### 生产注意
`guest` 适合"未登录/匿名"冒烟。真实业务应在 web 端录入客户信息后 `POST /api/customers`
（server 代理 → runtime `POST /customers`，带 metadata/标签/变量），把会话绑定到真实 `customer_id`
——客户变量才能驱动旅程分支（如 `isSensitive=true` 命中敏感分支）。

---

## 4. 会话创建：点击发送时才 POST /sessions

前端不"预建"会话，而是在**第一次发送消息时**才创建（`session-view.tsx` `createSession`）：

```ts
postData('sessions?allow_greeting=false', {customer_id, agent_id, title})
```

即 `POST /sessions`，query 带 `allow_greeting=false`，body 为 `{customer_id, agent_id, title}`，
runtime 返回真实 `session.id`（前端之前用的 `NEW_SESSION_ID` 只是占位）。

### 与 server BFF 的关系
- `POST /api/sessions`（阶段3.3）：server 代理转发 runtime `POST /sessions`；
  **同时往 MySQL `user_sessions` 落一行台账**（`user_id/session_id/agent_id/title/status/时间`），
  供"按用户查会话列表"（3.4/3.10）。
- 事件详情事实源仍在 runtime；MySQL 只是用户维度的可查询索引。

---

## 5. 消息发送与事件流

`session-view.tsx` `postMessage` → `POST sessions/{id}/events?moderation=none`：

```json
{"kind": "message", "source": "customer", "message": "文本"}
```

- `message` 是**字符串**（不是对象）。
- `moderation=none` 关闭审核（生产可开 `auto`，见 docs/03-production/02-用户输入审核.md）。
- 事件流订阅：`EventSource → GET /sessions/{id}/events`（SSE），
  前端按 `offset` 增量拉取/续传；status 事件带 `matched_guidelines/matched_journeys`。

### 事件 DTO 结构（易踩坑）
**`source`/`kind` 在事件对象顶层，`data` 内才是 message/status/participant**：

```json
{"id": "...", "source": "ai_agent", "kind": "message", "offset": 3,
 "data": {"message": "...", "participant": {...}}, ...}
{"source": "system", "kind": "status", "data": {"status": "processing", "data": {...}}}
```

解析时勿从 `data` 里取 `kind`。

---

## 6. 框架 REST 接口清单（/chat 用到的）

| 动作 | 方法 + 路径 | Body / 备注 |
|---|---|---|
| 拉 agent | `GET /agents` | 仅已加载实体 |
| 拉客户 | `GET /customers` | 首项永远含内置 `guest` |
| 建客户 | `POST /customers` | 生产：真实客户（metadata/标签/变量） |
| 建会话 | `POST /sessions?allow_greeting=false` | `{customer_id, agent_id, title}`；忽略 body 里传入的 `id`（runtime 自生成） |
| 发消息 | `POST /sessions/{id}/events?moderation=none` | `{kind:"message", source:"customer", message:"..."}` |
| 收事件 | `GET /sessions/{id}/events` | SSE；`wait_for_data=0` 立即返回、默认长轮询 60s |
| 会话详情 | `GET /sessions/{id}` | 含 customer_id/agent_id/mode |

> 前置约束：**建会话前客户必须已存在**。若 `customer_id` 不存在，引擎 `_load_context`
> 读客户会抛 `ItemNotFoundError: Item '<id>' not found`（背景任务日志 "Awaited task raised
> an exception"，无 AI 回复）。`POST /sessions` 本身不校验客户存在。

---

## 7. 本仓库 BFF 的代理映射（阶段3.3）

| web 调用 | server（本仓库） | runtime（Parlant 框架 REST） | 附加 |
|---|---|---|---|
| `GET /api/agents` | 定义层 + runtime loaded 合并 | `GET /internal/agents` | 已有 |
| `POST /api/customers` | 转发 | `POST /customers` | 3.3 |
| `POST /api/sessions` | 转发 + 落 MySQL 台账 | `POST /sessions` | **台账写入闭环** |
| `GET /api/sessions?user_id=` | 读 MySQL 台账 | —（事件详情回 runtime） | 3.4/3.10 |
| `POST /api/sessions/{id}/events` | 转发 | `POST /sessions/{id}/events` | 3.3 |
| `GET /api/sessions/{id}/events` | **SSE 透传**（streaming 转发） | `GET /sessions/{id}/events` | 3.3，断线按 offset 续传 |
| `GET /api/sessions/{id}` | 台账 + runtime 详情合并 | `GET /sessions/{id}` | 3.3/3.10 |

> 原则：**创建/事件走框架 REST（经 server 代理），server 只额外做用户维度台账**；
> 事实源始终在 runtime。
