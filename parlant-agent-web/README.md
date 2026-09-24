# parlant-agent-web

**统一前端**：Agent 工作台（AgentStudio）。一个工程两个模块——

1. **Agent 首页**（onboarding，无侧栏）：选择/搜索/筛选 Agent，点击进入。
2. **带浅色侧栏的工作台**（点击左上品牌回首页，切换 Agent = 侧栏「当前 Agent」下拉）：
   - **Agent 构建**（`/build`）：11 个组件页（指南 / 旅程 / 变量 / 术语表 / 预设话术 / 工具 / 检索器 / 关系 / 观察 / 基础信息 / 边界 / 高级），组件导航带 Parlant 英文术语括号。
   - **模拟对话**（`/simulate`）：会话边栏可收起、新对话对话框（当前草稿 / 线上版本）、SSE 流式 + session_messages 历史。
   - **追踪与观测**（`/obs`）：会话记录分页 + 消息级历史只读视图（无输入框）。
   - **自动仿真**（`/auto-sim`，占位，阶段6）、**版本历史**（`/build/versions`，占位，阶段4）、**设置**（占位）。

> 桌面端优先；设计稿 `design/agentstudio/`（v3.2，7 页）。

## 技术栈

Vite + React 19 + TypeScript + Tailwind CSS v4 + zustand（状态）+ react-router-dom v7（路由）。

## 快速启动

```bash
npm install
npm run dev
```

- 开发地址 `http://localhost:5173`。
- Vite 把 `/api` 代理到 parlant-agent-server（`http://127.0.0.1:8081`），前端零 CORS 直连（见 `vite.config.ts`）。
- **需先启动后端**：parlant-agent-server（8081）；runtime（8000）用于会话问答/草稿试跑。

## 脚本

| 命令 | 说明 |
|---|---|
| `npm run dev` | Vite dev server（HMR） |
| `npm run build` | `tsc -b && vite build` 类型检查 + 打包 |
| `npm run lint` | oxlint |
| `npm run preview` | 预览构建产物 |

## 代码结构（src）

```
src/
├── main.tsx            # 路由表：/ 首页（无侧栏）；/build /simulate /auto-sim /obs /settings（AppLayout 内）
├── App.tsx             # Vite 模板残留（未挂路由，可删；真实入口是 main.tsx）
├── AppLayout.tsx       # 浅色侧栏 shell（品牌/当前 Agent 下拉/导航）
├── components/         # Sidebar / AppLayout / Icons
├── api/
│   ├── client.ts       # API 客户端（agentsApi / customersApi / sessionsApi，全走 BFF）
│   └── types.ts        # 与 parlant-agent-server 的契约类型（Agent / Session / SessionMessage / ...）
├── pages/
│   ├── Home.tsx        # Agent 首页（onboarding）
│   ├── Build.tsx       # 构建页布局 + 组件导航
│   ├── build/          # 各组件配置页：Basics / Boundaries / Guidelines / Journey /
│   │                   #   TableModules(变量·术语·话术·工具·检索器·关系·观察) / Advanced / fields
│   ├── Simulate.tsx    # 模拟对话（会话边栏 + 新对话对话框 + SSE 流式 + 历史）
│   ├── Observability.tsx  # 追踪与观测（会话记录 + 只读对话视图）
│   └── Placeholder.tsx # 占位页（版本历史 / 自动仿真 / 设置）
└── store/              # zustand：app（Agent 列表/当前 Agent）、build（草稿编辑状态）
```

## API 契约要点（对应 parlant-agent-server）

- `GET /api/agents` → `{agents: AgentInfo[]}`（agent_id / published_version / latest_version / loaded）
- `POST /api/agents`：保存草稿（完整 `agent-definition.json`）
- `POST /api/agents/{id}/publish`：发布（可带 version，空则自动 patch+1）
- 会话：`POST /api/sessions`（body 带 `agent_id/customer_id/source/mode`）；SSE 用 `EventSource` 消费 `/api/sessions/{id}/events?min_offset=`
- 发消息：`POST /api/sessions/{id}/events`，**`request_id/user_id/user_name` 用 query 参数**（URL 编码，中文安全）；`request_id` 前端生成（uuid），用户提问与 Agent 回复共用，用于消息历史/trace 关联
- 消息历史：`GET /api/sessions/{id}/messages`

## 会话页行为

- 会话列表按**当前 Agent + `source=simulate`** 查台账，支持删除。
- 新对话对话框：选 Agent + 来源（**当前草稿** = 试跑 `{agent_id}@draft` 实例 / **线上版本** = published）+ 传 user 信息。
- 观测页点开会话是**只读视图**（无输入框）。

## 样式约定

- Tailwind v4（`@import "tailwindcss"` + CSS 变量，见 `index.css`）；浅色主题、`--primary`（indigo）等语义变量。
- 图标用内联 SVG（`Icons.tsx`），不用 emoji。
