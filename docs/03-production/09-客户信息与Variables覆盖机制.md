# 客户信息与 Context Variables 使用机制（自研源码分析）

> 自研分析（非官方直译），2026-09-22，依据 Parlant v3.3.1 本地源码
> `src/parlant/core/engines/alpha/engine.py`、`src/parlant/core/entity_cq.py`、
> `src/parlant/core/context_variables.py`、`src/parlant/sdk.py` 逐行核实。
> 用途：澄清"客户信息怎么用、Variables 怎么解析、会话/客户级能否覆盖 Agent 构建默认值"，
> 作为自动仿真（阶段6）与模拟对话（阶段3）的实现依据。

---

## 1. 客户信息（Customer）怎么被框架使用

引擎每次处理会话都会 `read_customer(session.customer_id)`（`engine.py:458`），客户实体参与三件事：

| 客户字段 | 用途 | 源码位置 |
|---|---|---|
| `name` | 消息参与方 display_name（气泡署名） | `engine.py` `_load_context` → participant |
| `tags` | ① 变量取值优先级键 `tag:<tag_id>`；② 驱动"客户相关指南匹配"（customer-dependent guideline matching） | `engine.py:_load_context_variables` 的 key 列表 |
| `id` | 变量取值**最高优先级**键（客户级覆盖） | 同上，key=customer.id 排第一 |
| `metadata(extra)` | **仅存储，不直接注入 LLM 上下文** | 只在 customers.py 持久化复制 |

> **要点**：想让"客户事实"影响 Agent 行为，正确做法是**客户级 Context Variable**（把客户事实写进变量），
> 而不是塞 metadata——metadata 不会出现在 LLM 提示里。

---

## 2. Context Variables 解析优先级（核心机制）

引擎 `_load_context_variables`（`engine.py:1121`）对每个变量按**重要性顺序**取第一个非空值：

```
keys_to_check_in_order_of_importance = (
    [context.customer.id]                        # ① 客户级值（最高优先级）
    + [f"tag:{tag_id}" for tag_id in customer.tags]  # ② 客户标签级值
    + [Tag.for_agent_id(agent.id).id]            # ③ Agent 级值（= Agent 构建默认值）
    + [ContextVariableStore.GLOBAL_KEY]          # ④ 全局值
)
```

解析后的变量以 `{变量名: {value, description}}` JSON 注入 LLM 提示（`context_variables_to_json`）。

**值在哪存**（SDK 辅助方法，sdk.py）：
- `set_value_for_agent(agent, value)` → key = `agent:<agent_id>`（**Agent 构建默认**；我们的
  `agent_loader.py:197` 加载定义时即 `variable.set_value_for_agent(agent, default_value)`）
- `set_value_for_customer(customer, value)` → key = `customer.id`
- `set_value_for_tag(tag_id, value)` → key = `tag:<tag_id>`
- 全局 → `ContextVariableStore.GLOBAL_KEY`

---

## 3. 会话/客户级能否覆盖 Agent 构建默认值？——能

**Parlant 没有"会话级变量"**，覆盖是按**客户维度**：

```
PUT /context-variables/{variable_id}/{customer_id}   body: {"data": {...}}
```

- 写入后该变量在 key=`customer_id` 有值 → 引擎按优先级 `customer.id`（第一）取到 → **覆盖 `agent:<id>` 默认值**。
- **同一 customer 的所有会话共享该覆盖值**（值挂在 customer，不挂在 session）。

> 推论（自动仿真/模拟对话的"换身份"技巧）：
> 每个身份用**独立 customer_id**，各自 PUT 客户级变量 → 同一 Agent、不同客户可得到不同旅程走向
> （如 `isSensitive=true` 命中敏感分支），互不干扰。

---

## 4. REST 端点速查（BFF 阶段3 代理）

| 动作 | 端点 | 说明 |
|---|---|---|
| 建客户 | `POST /customers` | body `{name, id?, metadata?, tags?}` |
| 建变量 | `POST /context-variables` | 定义变量（name/description/tool/refresh） |
| 读变量列表 | `GET /context-variables` | `include_values=true` 时带各 key 的值 |
| **设客户级值** | `PUT /context-variables/{variable_id}/{customer_id}` | body `{"data": ...}`；**覆盖 Agent 默认** |
| 读某 key 值 | `GET /context-variables/{variable_id}/{key}` | key 可为 customer_id / tag:* / agent:* / global |

> 注：`POST /sessions` body 只含 `customer_id/agent_id/title`，**不带 variables**；会话变量 = 客户级变量。

---

## 5. 自动仿真实现思路（阶段6，基于以上机制）

每个仿真 run：
1. **独立客户**：`POST /customers`（name/metadata/tags，如 `isSensitive` 标签）
2. **客户级变量覆盖**：依"执行说明"PUT 变量值（key=新 customer_id）→ 覆盖 Agent 默认
3. **建会话**：`POST /sessions`（绑定该 customer）
4. **循环对话**：`POST /sessions/{id}/events` 发消息 → SSE 收 Agent 回复 →
   LLM 依"用户背景/目标 + 对话步骤 + 上一条回复"生成下一问 → 再发
5. **终止**：达到最大轮次 / 画像目标达成 / Agent 明确结束 → 落执行记录（阶段6 sim_runs）

> 实现阶段已统一归并到 **阶段6**（见 `plan/阶段6-自动仿真与对话测试.md`），本仓库 web 的
> 自动仿真页面（`design/agentstudio/06-auto-simulation.html`）作为设计稿先行。
