# Agent 构建 · 全模块设计规格（v1 供确认）

> 状态：**待确认**（2026-09-23）。依据 `docs/02-concepts/` 各实体文档 + `agent-definition.json`（样例 onb-094c4bbe2663）
> 逐模块定义 **comp-nav 点击切换 → 列表(list-pane) + 检查器(inspector)** 的界面交互。
> 骨架/配色沿用 `design/agentstudio/02-workbench.html`（三栏：组件导航 | 列表 | 检查器，ctxbar 常驻）。
> 统一原则：**编辑即草稿**（顶部"3 处未发布更改"徽标）、保存草稿 / 发布新版本（确认弹窗）、模块计数、搜索/筛选。
> 复杂实体（指南/旅程）用 **列表+检查器（master-detail）**；简单实体（变量/术语/话术/工具/检索器/关系）倾向**表格 + 行内编辑**（待确认 §确认）。

---

## 0. 工作台统一骨架（已出稿，各模块复用）

```
┌ ctxbar（返回首页 + 当前Agent + 未发布徽标 + 版本 + [导出JSON][试跑][保存草稿][发布新版本]） ┐
├──────────┬───────────────────────────────┬──────────────────┤
│ comp-nav  │  list-pane（模块列表/表格）      │  inspector 检查器  │
│ 196px     │  顶部：搜索 + 筛选 + [新建]       │ 400px，随选中变化  │
└──────────┴───────────────────────────────┴──────────────────┘
```

- comp-nav 分组：Agent 定义（基础信息 / 边界与开场白）/ 上下文工程组件（指南 / 旅程 / 变量 / 术语表 / 预设话术 / 工具 / 检索器）/ 高级（关系 / 观察）
- 每模块列表行可「删除」（✕/垃圾桶，确认弹窗）；检查器底部「删除 / 取消 / 保存修改」。

---

## 1. 基础信息（Basics）

**非列表模块**：点选后 list-pane 隐藏，inspector 变**全宽表单**。

| 字段 | 类型 | 来源(agent-definition.json) | 说明 |
|---|---|---|---|
| 名称 | 文本 | `agent.name` | 必填 |
| Agent ID | 只读 mono | `agent.id` | **不可改**（唯一键） |
| 版本 | 只读 mono | `agent.version` | 发布时递增 |
| 描述 | 多行 | `agent.description` | 身份/职责 |
| 默认语言 | 下拉 | `agent.default_language` | zh-CN 等 |
| 标签 | chips | `agent.tags` | 可加可删 |
| 组合模式 | 下拉 | `agent.composition_mode` | fluid / strict / loose（全局，影响话术/指南组合） |
| 元数据 | JSON | `agent.metadata` | 可折叠 JSON 编辑 |

**交互**：编辑即草稿；名称/描述改动不即时发布。

## 2. 边界与开场白（Boundaries）

**非列表，全宽表单**（多段式）：
- **允许** `boundary.allowed[]`：列表，每项「允许做什么」文本框 + 添加/删除
- **禁止** `boundary.prohibited[]`：同上
- **紧急兜底** `boundary.emergency_action`：多行（遇到无法处理时的兜底话术）
- **开场白** `utterances.greeting[]`：多条模板列表（每次会话开场随机/依次）
- **兜底** `utterances.timeout_fallback` / `system_error_fallback`：多行
- 交互：段内增删条目；预览（在模拟对话中试跑开场白）。

## 3. 指南（Guidelines）✅ 已出稿（02-workbench）

**列表**：条件(cond) → 动作(action)、严重级别 tag、优先级、绑定标签（旅程/话术/工具）。
**检查器**：条件/动作 textarea、严重级别(低/中/高)、优先级(数值)、启用开关、绑定预设话术(chips)、
绑定旅程/状态(chips)、命中时更新变量(键=值)、删除/取消/保存。
**补充字段（新设计）**：组合模式、category(global/journey)、scope、依赖指南、绑定检索器、track 开关。
**筛选**：全部旅程 / 严重级别 / 绑定工具。

## 4. 旅程（Journeys）✅ 画布已出稿（03-journey-editor）

**列表**：标题、入口节点、状态数、优先级、触发器（主 trigger）。
**画布**（journey 模块默认视图）：节点色编码 **chat=靛蓝 · tool=绿 · fork=琥珀 · 终态=深灰**；
点阵网格 + 转移线（条件标签）；校验条（缺失分支/死节点）。
**检查器（随选中节点）**：chat_state/tool_instruction、type(chat/tool/fork)、转移列表（条件→to）、
variable_updates_on_enter/exit、工具绑定、变量绑定。

### 旅程配置字段审计（2026-09-23，对照 agent-definition.json + Parlant 源码）

**已补 UI 字段**（依据 agent-definition.json 盘点缺失 + SDK 确认生效性）：
- **旅程级**：title、description、entry_node、triggers、**composition_mode**、**priority**、**business_goal**（schema）
- **状态级**：title、type、chat_state/tool_instruction、description、**composition_mode**、**priority**、
  **tool_state（工具节点真正调用的工具，MultiSelect 含内置 variable_update/journey_node_counter）**、
  **canned_responses**（schema）、**retrievers**（schema）、**variable_updates_on_enter**（schema，JSON）
- **转移级**：condition、to、**canned_responses**（SDK create_transition 支持，**生效**）、
  **response_mode / timeout_branch / keywords**（schema）

**生效性判定（源码核实）**：
- **生效**：journey priority/composition_mode；state type/action/tools(tool_state)/composition_mode；
  transition condition/to/**canned_responses**
- **schema-only（v3.3.1 引擎未消费，保留配置）**：state canned_responses/retrievers/priority、
  variable_updates_on_enter/exit（v3.3.1 变量更新靠 tool_state 里的 `variable_update` 工具）、
  transition response_mode/timeout_branch/keywords、journey business_goal/sop_type/retrievers/dependencies/status
- **loader 已补映射**：journey priority、state composition_mode、transition canned_responses（此前配置了也不生效）
**旅程级编辑**：标题/描述/业务目标(sop_type)/入口节点/触发器(triggers[])。
- 从 JSON 看，旅程状态含 `chat_state`/`tool_instruction`、`type`、`transitions[]`（transition_id/condition/to/
  keywords/intent/topic_terms/timeout_branch/response_mode）、`variable_updates_on_enter/exit`、`tool_state[]`。

## 5. 变量（Variables）— 表格 + 行内编辑（建议）

**表格列**：名称 | 类型 | 默认值 | 描述 | 工具(动态) | 标签 | 操作
**行内/检查器字段**：
| 字段 | 类型 | 来源 | 说明 |
|---|---|---|---|
| 名称 | 文本 mono | `name` | 如 isSensitive |
| 类型 | 下拉 | `type` | boolean / string / number / … |
| 默认值 | 自适应控件 | `default_value` | boolean→开关；number→数字；string→文本 |
| 允许值 | chips/JSON | `allowed_values` | 枚举约束 |
| 描述 | 多行 | `description` | 语义 |
| 工具 | 下拉 | `tool` | 为空=静态值；绑定工具→动态刷新 |
| 刷新规则 | 文本 | `freshness_rules` | cron 表达式（配合工具） |
| 绑定客户字段 | 只读 | `bound_to` | 与客户 profile 的映射 |

**交互**：新增变量按钮；默认值按类型渲染；工具绑定提示"命中时由工具刷新"。

## 6. 术语表（Glossary）— 表格 + 行内编辑（建议）

**表格列**：词条 | 同义词 | 描述 | 操作
**检查器字段**：name、synonyms[]（逗号分隔 chips）、description（语义）。
- 样例：`提前结清`（同义词：提前还款,结清,一次性还款）。

## 7. 预设话术（Canned Responses）— 列表 + 检查器

**列表**：标题、模板预览（截断）、信号数、绑定（journey/字段依赖）。
**检查器字段**：模板（多行，支持 `{{var}}` 插值提示）、标题、signals[]（触发信号）、
field_dependencies[]（从对话抽取字段）、usage_context、描述。
- 提示：组合模式影响话术如何与 AI 生成拼接（fluid/loose）。

## 8. 工具（Tools）— 表格 + 检查器（JSON schema 编辑）

**表格列**：名称 | 来源(builtin/remote) | 服务 | 超时 | consequential | 类型
**检查器字段**：
| 字段 | 类型 | 来源 | 说明 |
|---|---|---|---|
| 名称/描述 | 文本 | `name/description` | 只读（builtin）或可改（remote） |
| 来源 | 只读 | `source` | builtin（引擎内置：journey_node_counter/variable_update/tavily_search）或 remote 服务 |
| 服务/远端名 | 只读 | `server_id/remote_name` | 挂接的 ToolService |
| 入参 schema | JSON 编辑器 | `input_schema` | 参数约束（编辑器 + 校验） |
| 入参字段 | 表格 | `input_fields[]` | name/type/required/desc |
| 超时 | 数字 | `timeout_seconds` | 秒 |
| 重试 | 数字 | `retry` | |
| 重要结果 | 开关 | `consequential` | 命中后重新评估指南 |
| 可编辑 | 只读 | `editable` | builtin 通常不可编辑 |

**交互**：新建工具 = 选服务（remote service）→ 填名称/描述/schema。

## 9. 检索器（Retrievers）— 表格 + 检查器

**表格列**：名称 | 类型(ragflow_http…) | endpoint | collection | top_k | 状态
**检查器字段**：title/description、type、连接配置（endpoint/collection/db_path/document_ids）、
检索参数（top_k/fetch_limit/min_score/context_min_score_default/min_query_length/timeout_seconds/
term_rewrite_enabled）、knowledge_scope、metadata_filter / customer_metadata_filter_map、状态(active/inactive)。
- 提示：RAG 型检索器需先配置后端（RagFlow/向量库），未初始化时列表标"未初始化"（`initialized` 标记）。

## 10. 关系（Relationships）— 列表 + 新建（建议 MVP：查看 + 基础新建）

**列表**：source(实体:id) → kind → target；kind 色编码（蕴含/优先级/依赖/消歧）。
**检查器/新建**：source 实体（指南/旅程/工具/关系…）、kind、target 实体、触发说明。
- 当前样例 relationships=[]，MVP 提供列表 + 「新建关系」引导（选择源/目标/类型）。
- 参考 docs/02-concepts/08：蕴含(Entailment)/优先级(Priority)/依赖(Dependency)/消歧(Disambiguation)。

## 11. 观察（Observations）— 类似指南（观察性指南）

**列表**：条件 → 动作（与指南同构，但触发时机=观察性）。
**检查器**：同指南（条件/动作/严重级别/优先级/绑定）。
- 当前样例 observations=[]，MVP 列表 + 新建。

---

## 待确认（影响实现）

1. **简单实体的形态**：变量/术语/话术/工具/检索器/关系 → **表格 + 行内编辑**（推荐，信息密度高）vs 与指南一致的 **列表 + 检查器**？
2. **旅程默认视图**：进旅程模块直接进**画布**（03-journey-editor），还是先列表再点开画布？
3. **关系/观察**（当前 0 数据）：MVP 只做**列表 + 新建引导**，完整编辑留后续？
4. **基础信息/边界**：全宽表单（隐藏 list-pane）是否 OK，还是也要双栏留白？
5. **组合模式**：agent 级一个开关（fluid/strict/loose）放基础信息，各组件不再单独设？
6. 是否需要把 02-workbench 改造成**模块可切换的交互原型**（点 comp-nav 切换右侧模块），还是按本规格逐模块独立实现？
