# 阶段4：Agent 配置管理模块（并入 parlant-agent-web）

> 目标：在 `parlant-agent-web` 中实现**配置管理模块**（原 parlant-agent-admin 的全部能力并入）——管理 Agent 及其全部上下文工程组件，支持 `agent-definition.json` 导入导出与版本发布/回滚；后端走阶段3 的 `parlant-agent-server /api/agents/*`。
> 对应参考文档：`docs/02-concepts/*`（逐组件配置含义）、`docs/04-execution-chain/02-核心模块源码地图.md`
> 设计：用 `frontend-design` 或 `ui-ux-pro-max` skill 产出高质感、非模板化的界面（`design/admin/` 已有 4 张高保真设计稿，可复用）。
> **2026-09-22 调整**：`parlant-agent-admin` 独立应用取消，本阶段从"独立前端工程"改为"parlant-agent-web 的配置管理模块"；后端从 runtime `/admin/*` 改为 server `/api/agents/*`。

---

## 交付物

- `parlant-agent-web` 配置管理模块（React + Vite + Tailwind + shadcn/ui），路由挂 `/admin/*`
- Agent 列表 / 新建 / 编辑 / 版本 / 发布
- 各上下文工程组件的配置界面（指南/旅程/变量/术语/话术/工具/检索器/关系）
- `agent-definition.json` 导入 / 导出
- **版本向前 + 版本历史/差异对比**（发布前 diff；快速回滚/渠道部署挪阶段5）
- 对接 parlant-agent-server 的 `/api/agents/*`（定义 CRUD + 发布编排）

---

## 任务清单

### 4.1 信息架构（IA）
```
/select, /chat/:sessionId, /sessions   # 阶段3 聊天模块
/admin/agents                 # Agent 列表（卡片：名称/描述/版本/状态）
/admin/agents/new             # 新建（向导 or 直接导入JSON）
/admin/agents/:id             # 编辑工作台（左侧组件导航 + 右侧编辑区）
/admin/agents/:id/versions    # 版本历史 / 发布 / 回滚
/admin/agents/:id/simulate    # 对话仿真（调用 server 试跑）
```
工作台左侧组件导航对应上下文工程组件：
`基础信息 · 指南 Guidelines · 旅程 Journeys · 变量 Variables · 术语表 Glossary · 预设话术 Canned Responses · 工具 Tools · 检索器 Retrievers · 关系 Relationships · 边界 Boundary`

### 4.2 设计系统
- 复用 `design/admin/` 设计稿（agents 列表 / 工作台-指南 / 旅程编辑器 / 版本），信息密度优先：清晰 > 炫技；左侧深色导航 + 右侧明亮工作区。
- 与聊天模块共用设计 token，保持单应用内观感一致。

### 4.3 各组件编辑器
| 组件 | 编辑器形态 | 要点 |
|---|---|---|
| 基础信息 | 表单 | name/description/utterances/boundary/composition_mode |
| 指南 | 可增删列表 + 条件/动作/严重级别/优先级 | 支持绑定 journey/工具/变量更新 |
| **旅程** | **可视化状态机编辑器** | 拖拽节点(entry/chat/tool/fork)、连线(transition+condition)；这是**最复杂也最有价值的编辑器** |
| 变量 | 表格 | name/type/default/freshness_rules |
| 术语表 | 列表 | name/synonyms/description |
| 预设话术 | 列表 + 模板 | 支持 `{{变量}}` 占位提示 |
| 工具 | 列表 + 配置 | 内置开关；自定义 `@p.tool`；OpenAPI/MCP 接入 |
| 检索器 | 表单 | type(ragflow_http/qdrant)/endpoint/collection/top_k/min_score |
| 关系 | 图/列表 | 指南间 蕴含/优先级/依赖/消歧 |

### 4.4 JSON 导入 / 导出
- 导出：当前编辑态 → `agent-definition.json` 下载（用于备份/迁移）。
- 导入：粘贴/上传 JSON → Schema 校验（与后端 pydantic 规则一致）→ 错误定位 → 生成可编辑草稿。
- 前端先做即时反馈，后端校验为最终准绳。

### 4.5 版本与发布（版本向前 + 版本历史/差异对比）
> **2026-09-24 调整**：发布/回滚简化为"**版本永远向前** + 发布前差异对比 + 版本历史查看"；**快速回滚与"版本 × 渠道"部署演进到阶段5 的渠道部署（5.8）**——Agent 编辑页只需看历史版本、做版本差异对比，其余不动。

- **版本永远向前**：发布总是产生新版本（server 自动从已发布 patch+1，或指定唯一版本号），**不做回滚覆盖**——旧版本保留在历史中可查看/对比。
- 草稿编辑 → 保存（draft，`POST /api/agents`）→ 发布（`POST /api/agents/{id}/publish`，server 推送定义给 runtime 热加载）→ 线上生效。
- **发布前差异对比**：发布弹窗对「已发布版本 vs 当前草稿」做**结构化 diff**（按板块：基础信息/指南/旅程/变量/术语/话术/工具…列出 新增/删除/修改 清单与计数）；**无任何变更时提醒用户确认是否仍要发布**。
- **版本历史页**（`/build/versions`）：版本列表（版本号/状态/时间/操作人）+ 与已发布版本/任意两版本的**差异对比**；`POST /api/agents/{id}/rollback` 端点保留（server 已实现，UI 弱化——快速回滚走阶段5 渠道部署）。
- 发布后给"去聊天窗口试跑"入口（跳转聊天模块并带上该 agent）。

### 4.6 对接后端
- 全部 CRUD 走 server `/api/agents/*`（阶段3.2）。
- 发布/回滚结果以 server 返回为准（runtime 加载失败时状态不变，前端展示明确报错）。

---

## 依赖组件

| 组件 | 用途 |
|---|---|
| parlant-agent-server（阶段3 `/api/agents/*`） | 数据源与发布编排 |
| parlant-agent-runtime（阶段2 热加载） | 发布/回滚的实际执行者（经 server 中转） |
| 旅程编辑器 | 自研（React Flow 类库可加速） |
| `frontend-design`/`ui-ux-pro-max` skill | 视觉设计 |

---

## 验收标准

- [ ] 完整新建一个 Agent：填基础信息 + 配指南 + 画旅程 + 设变量 → 发布 → 在聊天模块生效
- [ ] 导入 `agent-definition.json`（提前结清样例）自动还原为可编辑结构
- [ ] 修改某条指南并发布，新会话行为变化；回滚后恢复
- [ ] 旅程可视化编辑器能正确表达 fork/chat/tool 状态与条件转移
- [ ] 全程不直连 runtime：网络面板里只有 server（8081）的请求

---

## 风险与提示

- **旅程编辑器复杂度**：fork 状态与条件转移最易出错，建议先做"只读可视化"，再做"可编辑"。
- **Schema 与 UI 同步**：definition schema 演进时，UI 表单与校验要同步改——把 schema 作为单一事实源生成表单（如 json-schema-driven form）。
- **版本 diff**：实现指南/旅程级的差异对比，能大幅降低"改了哪"的排查成本。
