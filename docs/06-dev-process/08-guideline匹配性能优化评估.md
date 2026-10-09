# Guideline 匹配性能优化评估（调用次数 & Prompt 体积）

> 状态：**方案评估完成，未开发**（2026-10-01）。用户要求"只做方案评估，不做开发"。
> 数据来源：langfuse trace `cc3356ea2e0345edba51a7dd2b87c65a`（普通轮：客户"我在考虑下，有点担忧"，
> 共 23 次调用）与 `12380c5481e348088c695042b7417833`（工具轮："帮我转人工吧"+transfer_to_human 执行，
> 共 28 次调用），均为**智能投顾 Agent 单轮**实测。源码依据：Parlant v3.3.1
> （`optimization_policy.py` / `generic_guideline_matching_strategy.py` /
> `guideline_low_criticality_batch.py` / `guideline_actionable_batch.py` / `observational_batch.py`）。
> 缓存命中率已由用户在 OpenRouter 后台核实正常，**不在本评估范围**。

---

## 1. 问题量化：单轮 23~28 次大模型调用

| 轮次 | 调用总数 | 构成明细 | matcher 输入合计（估 token） |
|---|---|---|---|
| **cc33 普通轮**（"我在考虑下，有点担忧"） | **23** | 话术模板选 1 + 工具调用 1 + 旅程节点选 2 + **指南逐条检查 19** | ~198K |
| **1238 工具轮**（"帮我转人工吧"） | **28** | 话术模板选 1 + 工具调用 2 + 旅程节点选 4 + **指南逐条检查 21**（初判+工具后重评 2 趟） | ~257K |

关键结构：一次"指南检查"调用**只查 1 条指南**（prompt 明写 `exactly 1 guidelines in the list`），
prompt 却 **29.7K~35K 字符 ≈ 8~12K token**（混合语料按 字符/3 粗估）。整个 matcher 趟 = 逐条重复 19~21 次。
另加旅程节点选择（2~4 次调用）、话术模板选择（1 次）、工具调用规划（1~2 次）。

**traces 存档**：`/tmp/trace_cc33.json`、`/tmp/trace_1238.json`。

## 2. 根因一：批大小策略——为什么逐条

路由（`generic_guideline_matching_strategy.py` `create_matching_batches`）把候选指南分 4 桶：

| 桶 | 路由条件 | demo 里谁进去 |
|---|---|---|
| **观察批** `GenericObservationalGuidelineMatchingBatch` | `not g.content.action`（无 action，与 criticality 无关） | 8 条 observations（criticality=medium） |
| **低优先级批** `GenericLowCriticalityGuidelineMatchingBatch` | `g.criticality == Criticality.LOW` | gdl_vip_offer / gdl_high_return（crit=low） |
| **已应用批** | `g.track and g.id in 上一轮 applied_guideline_ids` | 各轮已命中过的指南 |
| **普通批** `GenericActionableGuidelineMatchingBatch` | 其余（medium/high criticality，有 action） | 7 条中/高指南 |

批大小（`optimization_policy.py:76` `BasicOptimizationPolicy.get_guideline_matching_batch_size`）：

```python
if hints.type == "GenericLowCriticalityGuidelineMatchingBatch":
    return guideline_count if guideline_count <= 10 else 10   # ← 只有低批 ≤10 全合并
if guideline_count <= 10: return 1        # ← 其它桶（含观察批）≤10 一律 1/批
elif guideline_count <= 20: return 2
elif guideline_count <= 30: return 3
else: return 5
```

于是现状：8 条观察 = 8 次调用、7 条中/高指南 = 7 次调用、2 条 low 指南也逐条。

**⚠️ 实测发现（修正早前口径）：低优先级合并批在本次 traces 里未生效。**
cc33 的 19 次检查**全部是** `exactly 1 guidelines` 的逐条调用，含 criticality=low 的
gdl_vip_offer / gdl_high_return。推断根因：demo 全部指南 `track=True`，多轮会话中 low 指南
已 `applied` → 路由进「已应用批」（逐条），绕过低批合并。源码的低批路径本身存在且格式更省
（`guideline_low_criticality_batch.py:309` 输出仅 `{"applies": {id: bool}}`、无 rationale、≤10 全合并），
只是被 `track` 路由架空了。**所以"合并低批"是待开启的能力，不是现状**（见 §4.1）。

> 附：trace 中出现的 "You are likely to explain that currently only one contract…" 等条件
> 不在当前发布版定义里（server `GET /api/agents/inv-advisor-demo?mode=published` 已核）——
> 说明运行时加载的定义比 `examples/inv-advisor-demo.json` / 当前 Mongo 发布版旧。
> **指南清单以 server 发布版为准，本评估的量化数字不受影响。**

## 3. 根因二：Prompt 体积与共享冗余

每个 matcher 调用 = **共享前缀**（GENERAL INSTRUCTIONS + Task Description + shots + Agent 身份 +
变量 + 术语表 + 客户/会话 + **完整交互历史** + OUTPUT FORMAT）+ **唯一部分**（本次要检查的 1 条条件）。

cc33 行级统计（19 次检查逐行求交集）：

- **62.8% 的 prompt 行在 19 次调用之间逐字节相同**（共享行合计 18.6K 字符/调用）；
- 纯冗余重复 ≈ **118K 估 token/轮**（`18.6K × 18 次重复 ÷ 3`）；
- 每次调用真正不同的内容仅 ~8.6K 字符（条件块 + JSON 模板内嵌条件）。

其他放大因素：

- **交互历史不截断**：共享前缀随轮数线性膨胀，多轮后每调用更胖；
- **shots 为模块级 `_baseline_shots`（4 组）**，每组都进共享前缀；
- **63%~84% 的检查结果是 `applies:false`**（cc33 12/19、1238 16/19）——大部分是负样本，
  投入产出比低（19 次大调用只为确认"这条不适用"）。

## 4. 优化方向（分层，按"风险→收益"排序）

### 4.1 开启并校准低优先级合并批（低风险，源码已备）
- 杠杆：注入自定义 `OptimizationPolicy`（DI 容器 `container[p.OptimizationPolicy]`）覆盖
  `get_guideline_matching_batch_size`，对 `GenericLowCriticalityGuidelineMatchingBatch` 返回
  `guideline_count`（≤10 全合并，天然如此）。
- 前提：让 low 指南真正进 low 桶——评估 demo 对 criticality=low 的指南**关 `track`**
  （或接受"首轮合并、后续已应用逐条"的部分收益）。
- 收益：2 条 low → 2 次 → 1 次；只影响推荐类软规则（VIP 推荐、高收益推荐），风险最低。
- 代价：合并批输出无 rationale，langfuse 里看不到逐条判定理由。

### 4.2 观察批合并 4~5/批（低风险，收益最大）
- 观察 = 无 action 指南，命中只标记"已发生"，不直接决定回复走向。
- demo 8 条观察在当前 19 次检查里占 8 次（42%）——是最大头。
- 调 `GenericObservationalGuidelineMatchingBatch` 批大小 4~5 → 8 次降为 2 次。
- 观察批 prompt 同样是 `exactly N guidelines` 一 call 多条件，parlant 已验证该格式可行。

### 4.3 中/高 criticality 指南 2~3/批（中风险，需 A/B）
- 普通批当前 1/批 → 2~3/批（`GenericActionableGuidelineMatchingBatch` 批大小）。
- **合规类保持 1/次**：criticality=high 的 gdl_risk_first / gdl_force_transfer / gdl_risk_match /
  gdl_canned_compliance 直接决定"拒荐/转人工/合规话术"等关键动作，逐条最稳。
- 其余 medium（同理心 / 个股 / 费率）可 2~3/批。

### 4.4 Prompt 裁剪（与批合并相乘，收益叠加）
- **shots 4→2**（保留 2 个高保真示例）；
- **交互历史截断**（只留最近 N 轮 + 首条，控制共享前缀膨胀）；
- 变量/术语表描述裁剪。
- 每一条都只减共享前缀；与批合并是**乘法关系**（19 次调用 × 前缀变小）。

### 4.5 前置过滤（现阶段不推荐）
- embedding 召回已在准备期常驻（`find_similar_documents` span），结果就是候选集本身；
  再加粗排过滤省不下调用数（embedding 每轮都在花），留作远期（few-shot 收敛后）。

## 5. 落地与验证（A/B）

**杠杆点**：runtime 装配时注入自定义 `OptimizationPolicy`，按 `hints["type"].__name__` 分流：

| 批类型 | batch_size 目标 | 效果（demo 单轮） |
|---|---|---|
| LowCriticality | `guideline_count`（≤10 全合并） | 2 → 1 |
| Observational | 4~5 | 8 → 2 |
| Actionable（medium） | 2~3 | ~3 → 1~2 |
| Actionable（high/合规） | 1 | 不变 |

**验证指标**（langfuse 各取 N 轮对比调整前后）：
1. **matched_guideline 集合一致性 ≥95%**（同一会话复跑，比对每轮命中集）——硬门槛；
2. journey.progress 分叉路径不变（`parlant.log` 或 langfuse）；
3. 话术命中不变（canned_template 选择结果）；
4. 端到端：单轮调用数 23 → ~8，matcher 输入 ~198K → ~60K 估 token。

**回滚**：重启 runtime 换回原 policy（DI 单例，无持久化状态）。

## 6. 术语澄清：criticality vs priority（两条正交轴）

| 字段 | 取值 | 决定什么 |
|---|---|---|
| **criticality**（严重级别） | low / medium / high | **匹配阶段怎么批**：low → 低优先级合并批（≤10 全合并）；medium/high → 普通批逐条；观察批由"无 action"决定（与 criticality 无关） |
| **priority**（数字优先级） | 0-100 | **命中后谁优先**：RelationalResolver 数值优先（如 gdl_risk_first=100 压过旅程） |

demo 里 low criticality 的两条恰好 priority 也低（40/30），但两者可正交配置。
落地批大小策略时只动 `criticality` 通道，勿动 `priority`（那是解析阶段的语义）。

## 附：本评估对早前口径的修正

- 早前表述"trace cc33 里低优先级指南已被合并"**不成立**：cc33/1238 中 criticality=low 的指南
  同样走了逐条检查（`exactly 1`），原因是 demo 全指南 `track=True`、已应用即绕开低批。
  低优先级合并是**待开启的能力**，本评估把它列为 §4.1 的首个落地项。
- 运行时加载的定义比 `examples/` 新：trace 含当前发布版没有的英文条件指南
  （"only one contract…"等）——核对定义时以 server 发布版为准。
