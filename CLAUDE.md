# Parlant 体系化学习工程 · 项目入口（CLAUDE.md）

> 给 Claude 看的项目总入口。定位、架构、启动方法、目录地图、关键约定都在这；再往下的细节见 `docs/`（学习资料）与 `plan/`（实施计划）。

## 一、这是什么

围绕 **Parlant v3.3.1** 体系化搭建的一套「**可配置、可调度、可观测**」客服智能体系统（学习 + 实战项目）。
核心资产：

- **`agent-definition.json`** 是 Agent 配置的单一事实源（schema 见 `parlant-agent-runtime/app/models/definition.py`）。
- **langfuse** 展示整体执行链路（OTLP 直投）。

## 二、三应用架构（当前形态）

```
parlant-agent-web ──REST/SSE──> parlant-agent-server :8081 ──HTTP/SSE──> parlant-agent-runtime :8000
                                   │ 定义层（Mongo，server 独占写）
                                   └─ 台账（MySQL：user_sessions / session_messages）
```

| 应用 | 定位 | 技术 | 端口 |
|---|---|---|---|
| **parlant-agent-runtime** | 执行引擎：`p.Server()` 加载 Agent、调度引擎（问答/旅程/工具）；**不直接面向前端**，Parlant REST/SSE 仅内网 | Python + FastAPI 包装 p.Server | 8000（REST/SSE）+ 8818（工具） |
| **parlant-agent-server** | BFF/元数据服务：定义层 **独占写** + 发布编排 + 会话代理 + SSE 透传；前端唯一入口 | Python + FastAPI（独立进程） | 8081 |
| **parlant-agent-web** | 统一前端：Agent 首页 + 浅色侧栏工作台（构建/模拟对话/追踪与观测/设置） | Vite + React 19 + TS + Tailwind v4 + zustand + router 7 | 5173（dev） |

**关键设计决策**：
1. **执行与元数据分离**：runtime 只装载定义 → 执行；定义层 Mongo 由 server 独占写，发布时 server 推 runtime 热加载，runtime 启动时反向从 server 拉 published。
2. **问答全链路经 server 代理**：web 不直连 runtime；SSE 透传回前端；鉴权/限流/CORS 集中在 server。
3. **配置与运行分离**：定义层（Source of Truth）→ runtime 加载器转换为 Parlant 实体（Agent/Guideline/Journey/Variable/Glossary/CannedResponse/Tool）。
4. **server↔runtime 现阶段同步 HTTP + SSE 透传**；消息队列（削峰/解耦/故障转移）推迟阶段5 多 pod。

## 三、启动顺序

```bash
# 前置：MongoDB（定义层）、MySQL（台账）、可选 Qdrant；根 .env 放 LANGFUSE_* 三件套
# 1. server（BFF）
cd parlant-agent-server && uv sync && cp .env.example .env && .venv/bin/python -m app.main
# 2. runtime（引擎；不可达 server 时降级本地示例，开发期可单独跑）
cd parlant-agent-runtime && uv sync && cp .env.example .env && .venv/bin/python -m app.main
# 3. web（前端）
cd parlant-agent-web && npm install && npm run dev   # localhost:5173，/api 代理到 8081
```

> 每个子项目自带 `README.md`（更详细）。

## 四、目录地图

```
parlant-study/
├── CLAUDE.md                 # 本文件：Claude 项目入口
├── plan/                     # 实施计划：README 总纲 + 阶段0~5（按新架构改写）
├── docs/                     # 学习资料（中文）
│   ├── 01-quickstart/ 02-concepts/
│   ├── 03-production/        # 生产实践（08 内置ChatUI分析、09 Variables覆盖、10 草稿试跑、
│   │                         #   11 内置工具、12 观测去hack化改造…）
│   └── 04-execution-chain/
├── parlant-agent-runtime/    # 执行引擎（见其 README）
├── parlant-agent-server/     # BFF（见其 README）
├── parlant-agent-web/        # 前端（见其 README）
├── design/                   # 设计稿（design/agentstudio/ v3.2 当前有效；admin/v1、chat/v2 历史稿）
├── .gitignore
└── .env                      # 根环境变量：LANGFUSE_*（不入库）
```

## 五、关键约定与陷阱（务必先读）

1. **Parlant 源码本地安装**：`parlant` 经 `[tool.uv.sources]` 指向 `../parlant` editable 安装（工作区外独立 repo）。**我们对 parlant 源码做过 6 处改动**（git 可查 diff），其中：
   - **必需 hack（勿还原）**：`litellm_service.py`（惰性导入 JinaAIEmbedder，Intel 机器无 torch wheel）、`opentelemetry.py`（OTLP timeout 30000 + console/HTTP 噪声采样）。
   - **上游 bug 修复**：`sdk.py` 评估任务名解析（`split("_")[-1]` → `removeprefix`，否则含下划线 id 启动崩溃）。
   - **观测插桩（技术债，待去 hack 化）**：`engine.py` / `journey_next_step_selection.py` / `gen_ai.py` 的日志与 span；方案见 `docs/03-production/12-观测插桩去hack化改造.md`，落地后 git checkout 还原这 3 处。
2. **定义层 ↔ 引擎实体 id**：加载器显式传旅程/状态 id（`jny_*`/`sta_*`，进全局存储）；**带 `@` 后缀的实例**（草稿 `{agent_id}@draft`）子实体 id 统一加后缀隔离，否则旅程 id 冲突报错、状态 id 静默覆盖。
3. **热加载旅程必须后台补评估**：`reachable_follow_ups`（分叉条件表）只由 SDK 启动评估产出；热加载（publish/rollback/@draft）实体由 `AgentLoader` `asyncio.create_task` 后台逐旅程评估（缓存 `parlant-data/evaluation_cache.json`，实测可达 8 分钟，阻塞会拖死 load/会话创建）。评估完成前 fork 暂不可推进。
4. **服务间 502 陷阱**：本机 macOS 系统代理（`:7899`）+ httpx `trust_env` 默认读 → 127.0.0.1 请求被转代理。**runtime↔server 全部 httpx 客户端 `trust_env=False` 直连**；server 的 `load_agent` 超时单独 600s。
5. **时间一律 UTC**（`datetime.now(timezone.utc).replace(tzinfo=None)`）；**request_id/user 用 query 参数传中文**（header 会 latin-1 乱码）；**消息历史落库靠 SSE 旁路**（前端必须始终开 SSE）。
6. **会话有效性在台账侧判定**（status=active 且未结束且未超时），不依赖 runtime sessions.json；runtime 会话/客户持久化 `session_store/customer_store="local"`（重启可续）。
7. **Parllant 陷阱**：建会话前必须先建客户（否则 ItemNotFoundError）；`POST /sessions` body 传 id 被忽略；事件 DTO 的 `source/kind` 在顶层、`data` 内才是 message/status；p.Server() 核心 store 默认 transient（实体不落盘，靠启动时重建）。

## 六、术语对照（简体中文 → Parlant 英文）

Guideline=指南 · Journey=旅程 · JourneyState=状态 · Canned Response=预设话术 · Context Variable=变量 · Glossary=术语表 · Tool=工具 · Retriever=检索器 · Relationship=关系 · Observation=观察 · AgentDefinition=定义。

## 七、当前进度速查

- **阶段0~2 完成**（环境 / runtime 最小可用 / 定义转换+多 Agent）。
- **阶段3 进行中**：3.1-3.4 + 消息历史 + 会话生命周期/渠道 + 草稿试跑 + 旅程配置审计 + 内置工具 + 版本规则 已实现并验证；web 聊天/构建页已能跑通定义加载与模拟对话。
- **待办**：web 配置管理完整化（阶段4）、自动仿真（阶段6）、runtime 生产化（阶段5：多 pod/HA/消息队列/版本实例隔离）、观测插桩去 hack 化（技术债）。

> 详细进度与排障结论见 `memory/`（Claude 自动记忆，不入库）与本文件第五节的约定。
