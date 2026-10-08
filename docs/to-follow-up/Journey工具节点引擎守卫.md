# Journey TOOL 节点引擎守卫（待办 · 未实施）

> 状态：**已知，方案评估完成，暂不实施**（2026-10-01）。属 Issue B 的根治手段；
> 当前先以 ① 定义加固（软约束，已落 demo 草稿）压低误判率。本文档给引擎守卫（硬约束）
> 的设计与插入点，方案定了再做。
> 配套：`docs/03-production/15-guideline匹配性能优化评估.md`（另一条优化线，勿混）；
> 原 Issue B 分析见 memory `http-tools-required-and-journey-tool-node-footgun.md`。

---

## 1. 问题（Issue B 复述）

**症状**：旅程的 **tool 类型节点**（如 `sta_B`，`tool_state=["assess_risk"]`）被模型误判为
**CUSTOMER DEPENDENT 步骤**——客户自报"我是稳健型投资者，C2级别" → 模型在节点选择输出里
`current_step_completed:true` + 直接推进到 `sta_C`，**全程没调 `assess_risk`**。

**实锤**（session `vIfrAP4jOr` turn 3，trace `56355d8b`）节点选择 rationale 原文：
> "客户已明确告知其风险承受等级为C2（稳健型），满足 CUSTOMER DEPENDENT 步骤的完成条件。"

**链条后果**：`assess_risk` 没执行 → `risk_assessed` 变量永为 false → `gdl_risk_first`（合规，
priority=100）永不解除 → 模板 `rsp_risk_not_assessed` 反复接管 → 死循环复读"先完成风险测评"。

**根因**：模型遵从性。prompt 里其实**已有**协议行
（`journey_next_step_selection.py:426` "TOOL EXECUTION: This step is considered complete
as long as the tool has been executed"），模型仍违规——所以①定义加固只是降低概率，**不根治**；
须靠引擎层确定性守卫兜底。

## 2. 要执行的不变量（与模型说什么无关）

> **TOOL 节点只有在它挂的工具已在本轮成功执行后，才允许被判"完成"并推进。**

信号源：`result.state.executed_tools`（`engine.py:571`；journey.progress 日志的
`executed_tools=['built-in:assess_risk']` 就是它）。

**边界说明（须按旅程语义放行）**：
- 只挡"离开 TOOL 节点时其工具未执行"这**一种坏法**（Issue B）。
- 若旅程存在"工具节点 → 客户拒绝 → 不调工具转人工"这类**合法不调工具**的分支，守卫需按
  转移条件语义放行，不得无条件拦截。当前 demo 里 `sta_B` 唯一出边 `tr_B_C`
  （"assess_risk 已成功返回"）暗含工具成功 → 可无条件要求 executed_tools 含 assess_risk。
- 远程工具非 2xx 是"成功返回 error 包"，也算 executed——守卫查的是"执行过"（防跳过），
  不是"执行且成功"（那是 422 必填拦截已覆盖的事）。

## 3. 插入点（按"是否动 parlant 源码"排序）

| 方案 | 改哪 | 原理 | 代价 | 推荐度 |
|---|---|---|---|---|
| **A. runtime EngineHooks** | 不碰 parlant 源码，runtime `app/` | 项目已用 `on_preparation_iteration_end` 钩子做 journey.progress 观测；钩子拿 mutable `EngineContext`，检测"路径从 TOOL 节点推进出去但该轮 executed_tools 无其工具"→ 改写 `context.state.journey_paths` 回 TOOL 节点 | 需先验证钩子时机（fires 在路径已计算后，改写能否影响该轮最终状态）；hooks 本意观测，拿来改状态略越界 | **首选**（符合去 hack 化） |
| **B. parlant 源码 `engine.py` `_list_journey_paths_from_guideline_matches`（:2143）** | 动 parlant 源码 | 状态推进权威点：写 `journey_paths[id]=path` 前校验 | 又一个源码 hack；可按"上游 bugfix"口径提 PR（类似 sdk.py 那次） | 次选（干净但侵入） |
| **C. parlant 源码 `journey_next_step_selection.py` 输出校验** | 动 parlant 源码 | 离模型决定最近：解析 JSON 后，当前节点 TOOL 且 `current_step_completed=true` 但无对应 staged tool event → 强制 `applied_condition_id="0"` | 耦合在 matcher 批内部 | 末选 |

## 4. 可验证性（怎么做算"完成"）

1. 用强一致复现脚本跑"客户自报 C2 等级"场景（复用 `/tmp/repro_chain.py` 思路）；
2. 断言：journey.progress 里 sta_B(5) 不越步 → 模型先调 assess_risk → `risk_assessed` 置位
   → 5→6 推进；`rsp_risk_not_assessed` 死循环不再出现；
3. 回归：已测评客户（画像 C4）仍走 sta_A→sta_C 跳过测评的合法分支，不被误伤；
4. 校验 published `1.0.2` 之外的 draft 行为——守卫对 publish/rollback/@draft 一律生效。

## 5. 与 ① 的关系

| | ① 定义加固（已落 demo 草稿） | ② 引擎守卫（本文档，未实施） |
|---|---|---|
| 性质 | 改模型看到的内容（软约束） | 引擎确定性校验（硬约束） |
| 改哪 | 定义 JSON / 构建页，零代码 | 引擎代码（A runtime / B、C parlant 源码） |
| 保障 | 降误判率，不保证 | 模型怎么判都拦得住 |
| 状态 | ✅ 已落 demo draft 槽 + examples | ⏸️ 待选方案再实施 |

**建议组合**：① + ②A（先验证 A 的钩子时机可干预，再决定是否上 B/C）。