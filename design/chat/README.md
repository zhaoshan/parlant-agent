# parlant-agent-web · AgentStudio 工作台（对话仿真 / 自动仿真 / 追踪与观测）

> 状态：**待确认 v2**（2026-09-22 按统筹反馈重构）。
> 核心理念：parlant-agent-web 是一个 **AgentStudio 工作台**，「对话仿真」= 工作台内的
> **模拟聊天 / 预览窗口**，由 AgentStudio（原 admin）工作台的「试跑」入口进入。
> 与 `design/admin/` 共用**同一套设计系统**（token / 字体 / 侧栏），产品是一体的。

---

## 1. 统一信息架构（chat 与 admin 同一份侧栏）

```
┌───────────────────────────────────────┐
│ ▍AgentStudio                            │
│   Agents（原 admin 列表/工作台/版本）     │
│ ▍仿真                                   │
│   对话仿真（手动预览窗口）               │
│   自动仿真（后台程序循环对话）           │
│ ▍观测                                   │
│   追踪与观测（会话记录 + 链路浏览，合并） │
│   设置                                  │
└───────────────────────────────────────┘
```

- 品牌：**AgentStudio** / "Agent 配置与仿真"。
- admin 4 页侧栏已同步更新为本结构（Agents 高亮）；chat 页各自高亮当前模块。
- 入口打通：AgentStudio 工作台右上角「试跑」→ 对话仿真·新对话（选身份）→ 聊天窗口。

## 2. 页面清单

| 文件 | 路由 | 说明 | 后端 API |
|---|---|---|---|
| `01-conversation.html` | 对话仿真 `/` | 工作台：**可收起会话边栏**（含"新对话"对话框=原 /select）+ 聊天主区 + **可折叠执行详情栏** | `GET /api/agents`、`POST /api/customers`、`POST /api/sessions`、SSE `GET /api/sessions/{id}/events` |
| `02-auto-simulation.html` | 自动仿真 `/auto` | 后台程序模拟客户：配置（Agent/客户画像/轮次/间隔）→ 运行 → 进度 + 逐轮日志（每轮 trace 链接） | 复用会话 REST + SSE；提问生成脚本 |
| `03-observability.html` | 追踪与观测 `/obs` | 页签「会话记录 / 链路浏览」：会话记录按轮展开、**每轮可打开 langfuse 链路** | `GET /api/sessions?user_id=`、langfuse |

## 3. 关键决策

1. **会话边栏可收起**（对话仿真页左侧，默认展开，可收起为 0 宽）。
2. **执行详情栏可折叠**（右侧 300px，默认展开，可折叠）。
3. **/select 并入**「新对话」对话框（对话仿真页内，选 Agent + 客户身份，含 guest 冒烟）。
4. **/sessions 并入** 追踪与观测（会话记录），对话仿真的会话边栏承担"切换会话"。
5. **自动仿真**独立菜单：后台任务「发消息 → 收 SSE → 按 Agent 回复自动生成下一问 → 再发」，循环至最大轮次/目标达成/Agent 结束。
6. **每轮可追溯**（新需求）：会话记录按**轮**展开，每轮带 `trace_id` + langfuse 链接 → 需在台账侧记录轮次（见 §5）。
7. **桌面端优先**；widget 部署方案后续单独设计（不占当前布局）。

## 4. 工具卡片（用户曾问）

AI 回合内嵌**可折叠工具调用卡片**：工具名（mono）+ 入参/结果 JSON；`tool_caller` 阶段顶部有
status chips。数据来自 SSE 事件流的 tool 事件。价值=工具过程可见。

## 5. 待后端配套（阶段3 计划更新）

- **对话轮次记录**：MySQL 需新增 `session_turns`（或台账内每轮子表）：session_id / turn_no /
  customer_msg / agent_msg / tool_count / trace_id / created_at。由 server 在 SSE 透传侧
  观察并落库（ai_agent message 事件带 trace_id），供追踪与观测"每轮打开链路"。
- **自动仿真**：server 增加"仿真运行"端点（启停 + 轮询），提问生成用客户画像脚本 + LLM，
  或先以固定脚本驱动（阶段3 可选实现，阶段5 强化）。
- **langfuse 跳转**：配置 langfuse base URL，前端组装 trace 详情页 URL。

## 6. 待确认

1. 自动仿真 v1 的提问生成：固定脚本（简单）vs LLM 按画像生成（真实但多一次调用）？建议先固定脚本。
2. 每轮记录触发点：server 侧 SSE 旁路解析落库（推荐，前后端都无感）vs 前端上报？
3. 追踪与观测的「链路浏览」tab：v1 直接跳 langfuse（当前稿占位）够不够，还是要内嵌面板？
