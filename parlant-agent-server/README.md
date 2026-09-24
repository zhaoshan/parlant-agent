# parlant-agent-server

**BFF / 元数据服务**：前端（parlant-agent-web）唯一后端入口。承载 Agent 定义 CRUD / 版本 / 发布编排（**定义层唯一写方**）+ 会话代理（REST + SSE 透传）。**本服务不承载 Parlant 引擎**——引擎在 parlant-agent-runtime（p.Server()）。

> 无状态、易水平扩展；与 runtime 的交互现阶段用同步 HTTP + SSE 透传（消息队列推迟到阶段5 多 pod）。

## 职责边界

| 职责 | 说明 |
|---|---|
| Agent 定义 CRUD/版本 | MongoDB `agent_definitions` 由本服务**独占写**；schema = `agent-definition.json` |
| 发布/回滚编排 | 发布=推送定义给 runtime `POST /internal/agents/{id}/load` 热加载 → 成功才置 published（旧版本 archived）；失败不改状态 |
| 会话代理 | 转发 Parlant REST（runtime `:8000`），建会话/发消息/查会话 |
| SSE 透传 | 订阅 runtime `GET /sessions/{id}/events?sse=true` 逐帧转发给 web，断线按 `min_offset` 续传 |
| 用户维度台账 | MySQL `user_sessions` / `session_messages`：会话台账、消息级历史（阶段5 还将承载用户/登录/权限） |

## 快速启动

```bash
# 0. 依赖
uv sync

# 1. 环境变量
cp .env.example .env   # 填 RUNTIME_BASE_URL / MONGO_URI / MYSQL_URI / PORT

# 2. 启动（需先有 MongoDB、MySQL；runtime 可在/不在，定义类接口可独立工作）
.venv/bin/python -m app.main
# 或 uvicorn app.main:app --host 0.0.0.0 --port 8081
```

服务监听 `0.0.0.0:8081`（8080 常被本机 Docker 进程占用，故取 8081）。

## 环境变量

见 `.env.example`：

| 变量 | 默认 | 说明 |
|---|---|---|
| `RUNTIME_BASE_URL` | `http://127.0.0.1:8000` | 下游 parlant-agent-runtime |
| `RUNTIME_TIMEOUT` | `30.0` | 常规请求超时（load 单独 600s，见下） |
| `MONGO_URI` | `mongodb://parlant:parlant-dev@localhost:27017/parlant?authSource=admin` | 定义层 |
| `MYSQL_URI` | `mysql+aiomysql://root:root123456@127.0.0.1:3306/parlant` | 会话台账 |
| `HOST` / `PORT` | `0.0.0.0` / `8081` | 服务监听 |
| `CORS_ALLOW_ORIGINS` | `*` | 跨域（生产收紧为 web 来源，逗号分隔） |

## 关键端点

### /api/agents/*（定义层，本服务独占写）

| 端点 | 说明 |
|---|---|
| `GET  /api/agents` | 列表（agent_id / published_version / latest_version / loaded，含 summary 计数） |
| `POST /api/agents` | 保存/创建（version=「draft」槽，每 agent 一个草稿；校验失败 422） |
| `GET  /api/agents/{id}` | 详情 + 完整定义 + 组件统计 |
| `GET  /api/agents/{id}/versions` | 版本历史 |
| `POST /api/agents/{id}/publish` | 发布（无 version 时 patch+1：`_next_version`；手动指定校验唯一/409）。流程：取 draft 槽草稿 → 定目标版本 → 推 runtime 热加载 → 落 target=published（旧 published 置 archived）→ 清空 draft 槽 |
| `POST /api/agents/{id}/rollback` | 回滚到指定已发布版本（也清 draft 槽） |
| `DELETE /api/agents/{id}/versions/{version}` | 单版本删除（不能删当前 published） |
| `DELETE /api/agents/{id}` | 停用：卸载 runtime 引擎实体（定义版本仍留库） |

> **草稿试跑**：`mode: draft` 的会话绑定 `{agent_id}@draft` 独立实例（`_ensure_draft_instance` 幂等加载），试跑行为不影响线上 published 实体；草稿会话关闭/删除后无剩余活跃时立即卸载 `@draft` 实例（`_release_draft_instance`）。

### /api/sessions/* 与 /api/customers/*（会话代理 + SSE 透传）

| 端点 | 说明 |
|---|---|
| `POST /api/customers` / `GET /api/customers` | 客户（转发 runtime；**建会话前必须先建客户**，或传内置 `guest`） |
| `POST /api/sessions` | 建会话：转发 runtime + 落 MySQL 台账（`source` 渠道：online/simulate/auto_sim；`mode`: draft/published） |
| `GET  /api/sessions` | 台账列表，`?agent_id=&source=&user_id=&offset=&limit=`（条件可空） |
| `GET  /api/sessions/{id}` | runtime 会话 + 台账字段合并 |
| `POST /api/sessions/{id}/close` | 主动关闭（台账标记 normal 正常结束） |
| `DELETE /api/sessions/{id}` | 删除台账 + 级联删消息历史 |
| `POST /api/sessions/{id}/events` | 发消息/事件（body 原样透传，如 `{kind,source,message}`） |
| `GET  /api/sessions/{id}/events` | **SSE 透传**（`sse=true`，min_offset/wait_for_data 透传；旁路解析 ai_agent 消息落 session_messages） |
| `GET  /api/sessions/{id}/messages` | 消息级历史（session_messages），可按 `request_id` 过滤 |

**请求上下文传递**：`request_id / user_id / user_name` 用 **query 参数**传（URL 编码 UTF-8）——header 传中文会 latin-1 乱码；server 注入事件 metadata 留存 runtime，用于消息历史落库与 trace 关联。

### /api/internal/*（面向 runtime）

| 端点 | 说明 |
|---|---|
| `GET /api/internal/published-agents` | 返回全部 published 定义的 agent_id/version/definition（runtime 启动拉取） |

### 其他

- `GET /health`：三项探活（本服务 + Mongo + MySQL，聚合展示）。

## 代码结构（app 包）

```
app/
├── main.py              # 装配：lifespan 建 连接层→仓储层→服务层，路由统一注册
├── config/settings.py   # 集中配置（读 .env）
├── models/api.py        # 请求/响应 DTO（SessionCreateBody / PublishBody / ...）
├── databases/           # 连接管理：MongoConnection / MySqlConnection（只出句柄，不写业务）
├── repository/          # 仓储层（注入连接句柄）
│   ├── agent_definition_repository.py   # agent_definitions（Mongo）
│   ├── user_session_repository.py       # user_sessions 台账（MySQL，SQLAlchemy async + aiomysql）
│   └── session_message_repository.py    # session_messages 消息级历史（幂等 upsert）
├── services/
│   ├── agents.py        # AgentDefinitionService：版本规则/发布编排/PublishError
│   └── sessions.py      # SessionService：代理 + 台账读写 + SSE 旁路消息记录
├── boundary/
│   └── runtime_client.py # RuntimeClient：runtime HTTP 客户端（httpx 异步 + SSE 流式订阅）
└── routers/             # health / api_agents / api_sessions(+customers) / api_internal
```

### 分层约定

- **连接层**（databases）只创建连接/句柄，不写业务逻辑；**仓储层**（repository）注入连接句柄，负责具体存取。
- **RuntimeClient 全部请求 `trust_env=False`**：本机若开系统代理（macOS `:7899`），httpx 默认 trust_env 会读 → 127.0.0.1 请求被转代理 → 目标不可达 502（服务健康时透传 loopback，联调好时坏）。**`load_agent` 超时单独 600s**——旅程评估可能跑数分钟（首次缓存未命中）。
- **服务间通信全部直连**：无代理、无 TLS（内网）。

## 数据模型（MySQL 台账要点）

- **会话有效性在台账侧判定**：`valid = status=active 且未结束且未超时`（超时默认 1 天）；`invalid_reason` = normal（正常结束）/ timeout（超时结束）。不依赖 runtime sessions.json。
- 会话字段含 `agent_instance_id / agent_version / agent_status`（草稿 = "draft"），可区分草稿会话与线上会话。
- **时间一律 UTC**：`datetime.now(timezone.utc).replace(tzinfo=None)`（曾用本地时区导致 last_message_at 与 created_at 不一致）。

## 与前端 / runtime 的关系

```
parlant-agent-web ──REST/SSE──> parlant-agent-server :8081 ──HTTP/SSE──> parlant-agent-runtime :8000
                                    │ 定义层（Mongo，独占写）
                                    └─ 台账（MySQL）
```

- 前端唯一入口是本服务；鉴权/限流/CORS 集中在本服务。
- 发布链路：本服务 push runtime 热加载 → 成功才更新定义层状态；runtime 启动反向拉取 published。
