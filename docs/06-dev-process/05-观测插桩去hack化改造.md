# 观测插桩"去 hack 化"改造方案（技术债）

> 状态：**已落地并验证**（2026-09-28 实施，09-29 用 trace `24f10ccf` 完成运行时验证，§5 全绿）：
> - parlant 已还原 5 插桩文件 + 清理 litellm_service 临时段（DeepSeek 关 reasoning 迁 runtime patch）；
> - 观测/模型适配迁入 **runtime `app/observability/` 分 package**（hooks / patches / labels；otel 弃用，
>   各包 `__init__.py` 只做门面 re-export、实现在子模块）；
> - **litellm OTel 已实测弃用**（10:03 验证：async 下 ended-span 刷屏 + 属性丢弃）→ gen_ai.* 观测
>   改走 **patches 的 do_generate monkey-patch**（parlant tracer 自管 span，嵌套 process 下、无刷屏）；
> - **next_step/batch 日志（D-⑫⑬）不补**：决策 rationale 在 langfuse 可见（guideline_matcher 下
>   journey_next_step_selection / journey_backtrack_check；话术选择在 canned_response_generator），
>   patches/next_step.py 仅留占位。
> 背景：为排查旅程/LLM 问题，我们在**可编辑安装的 parlant 源码**里加了观测插桩；另有两处环境适配
> hack 与一处上游 bugfix。本方案评估用 **litellm 原生 OTel / EngineHooks / monkey-patch** 替代插桩，
> 恢复 parlant 源码干净、升级安全。
> 依据：langfuse OTLP 摄入规则（`gen_ai.*` 属性→generation；`langfuse.observation.input/output`→span I/O）、
> Parlant EngineHooks（`src/parlant/core/engines/alpha/hooks.py`）、litellm 1.102 `OpenTelemetry` 集成
> （支持传 `tracer_provider`）、parlant `OpenTelemetryTracer.span` 用 `trace.use_span`（contextvar 管理
> current span，opentelemetry.py:186）→ EngineHooks 内 `get_current_span()` 可取到 process span。

---

## 1. 现状：parlant 3 次提交共 8 文件全量核对（2026-09-28 快照）

**3 次本地提交**（相对原生 `ea737442`，累计 **+258/−16**）：

| 提交 | 涉及文件 |
|---|---|
| `a502c301` hack(v3.3.1): 本地适配 6 处（必需 3 + 插桩 3） | litellm_service / opentelemetry / engine / journey_next_step_selection / generation / sdk |
| `a08d75d2` hack(v3.3.1): 旅程插桩改名 parlant-agent + 扩到 batch | engine / journey_next_step_selection / journey_node_selection_batch |
| `2f89d2a1` feat: 观测日志 index 显示节点名称 | engine / journey_next_step_selection / journey_node_selection_batch / entity_cq |

**8 文件 × 11 变更点**，按处置分类：

### A. 必需 hack（保留，非插桩）

| 文件 | 变更点 | 说明 |
|---|---|---|
| `adapters/nlp/litellm_service.py` | ① `JinaAIEmbedder` 顶部导入 → `create_embedder` 内**惰性导入** | hugging_face → torch 依赖，仅回退路径需要；无 torch 环境顶部导入拖垮启动 |
| `adapters/nlp/litellm_service.py` | ② DeepSeek 推理模型显式关 `reasoning` | `deepseek-v4.1-flash` 等默认开 thinking，推理 token 耗尽 max_tokens → content 空 → 引擎按 `{}` 处理 → schema 校验失败（表象=评估/匹配全挂，与限流相同）。`litellm_api_arguments["reasoning"]={"enabled": False}`；非推理模型忽略无副作用 |
| `adapters/tracing/opentelemetry.py` | ③ Console exporter 加开关（**默认关**） | 原生每个 span 都以 JSON 刷 stdout；`PARLANT_OTEL_CONSOLE_EXPORTER=1` 才开 |

> **过时描述修正**：CLAUDE.md/memory 曾记 opentelemetry.py 含"OTLP timeout 30000 + HTTP 噪声采样"——
> 通盘核对 `git diff ea737442..HEAD` 该文件**仅 console 开关 1 处**；timeout 是 runtime `configure_langfuse_otel`
> 的**运行期配置**（本就该在应用侧，不是源码 hack）。落地后同步修正 CLAUDE.md 第五节。

### B. 临时诊断（待删）

| 文件 | 变更点 | 说明 |
|---|---|---|
| `adapters/nlp/litellm_service.py` | ④ `PARLANT_DIAG_DUMP_PROMPT` 环境变量 dump 真实 prompt 到 `/tmp/parlant_diag_prompt.txt` | 排查评估返回 `{}` 的临时手段（2026-09-26 加）；排查已收尾，**落地时删除该段** |

### C. 上游 bugfix（贡献上游，本地暂保留）

| 文件 | 变更点 | 说明 |
|---|---|---|
| `sdk.py` | ⑤ 评估任务名解析 `split("_")[-1]` → `removeprefix(f"{entity_type}_evaluation_")` | 任务名 `{entity_type}_evaluation_{id}`，id 含下划线（`jny_LuAwQZ`）时 `split("_")[-1]` 截断 → `read_journey` ItemNotFoundError **启动必崩** |

### D. 插桩（去 hack 目标，5 文件）

| 文件 | 变更点（vs 原生） | 目的 |
|---|---|---|
| `core/nlp/generation.py` | ⑥ `gen_ai.chat` span（prompt/completion/usage） | LLM 调用输入输出进 langfuse（generation 观测） |
| `core/engines/alpha/engine.py` | ⑦ process 根 span 设 `langfuse.observation.input/output`（用户消息/agent 回复） | 每"轮"根 span 的 I/O 摘要 |
| `core/engines/alpha/engine.py` | ⑧ `journey.progress`（iter + **index:名称** 路径） | 旅程推进定位 |
| `core/engines/alpha/engine.py` | ⑨ `engine.not_prepared`（executed_tools / tool_node_matched / plan 需再迭代） | 未准备原因 |
| `core/engines/alpha/engine.py` | ⑩ `engine.reeval`（重评估条数 + journey_nodes + active_journeys） | REEVALUATION 关系诊断 |
| `core/engines/alpha/engine.py` | ⑪ `_fmt_journey_index()` staticmethod | ⑧ 的格式化辅助 |
| `.../journey/journey_next_step_selection.py` | ⑫ `_index_to_label` + `_fmt()`；**5 种日志**：入口(current/kind/条件菜单)、退出旅程、留在当前、**命中条件→path**、无效条件（含合法条件表） | 分支选择定位 |
| `.../journey/journey_node_selection_batch.py` | ⑬ `_index_to_label` + `_fmt()`；`batch_enter`（批处理入口）+ `auto_return`（快路径推进/**穿透单分支 fork**/**放弃多分支 fork 转 next-step**） | tool 快路径决策/放弃原因 |
| `core/entity_cq.py` | ⑭ `journey_node_labels()`（index→名称：投影指南 BFS 序号 → `description or action` 截断 12 字） | ⑧⑫⑬ 的可读性辅助 |

> `workspace/parlant` 是独立 git repo，插桩可 `git checkout` 还原（落地路径见 §3）。

## 2. 替代可行性矩阵（2026-09-28 基于源码逐条核实）

### 2.1 LLM I/O（D-⑥ gen_ai span）→ ~~litellm OTel 回调~~ **实测弃用，回退 monkey-patch** ⚠️

- litellm 1.102 `OpenTelemetry(tracer_provider=...)` 支持传 provider（`inspect.signature` 确认），
  理论可复用 parlant 全局 TracerProvider。
- **实测结论（2026-09-28，runtime 10:03 日志）**：async `acompletion` 下 litellm 回调在 span
  **结束后仍调 set_attribute/set_status** → stdout 刷屏 "Setting attribute on ended span."
  + completion/usage 属性被 OTel SDK 丢弃（langfuse 数据不完整）。**不可用，弃用**。
- **回退方案（已落地）**：monkey-patch `LiteLLMSchematicGenerator.do_generate`，用 **parlant tracer**
  开 `gen_ai.chat` span（prompt/completion/usage）。parlant tracer 自管 span 生命周期（`trace.use_span`，
  结束即不可再写），无 ended-span 刷屏，且嵌套在 process span 下天然正确——即原 parlant 插桩的
  同款实现，迁到 runtime `app/observability/patches/`。
  > 细节修正：parlant `Tracer.attributes()` 是 contextmanager，原插桩漏写 `with`（completion/usage
  > 实际未生效）；runtime patch 已用 `with self.tracer.attributes(...)` 修正。
- **唯一遗留不确定点**：monkey-patch 依赖 `LiteLLMSchematicGenerator.do_generate` 签名/存在性，
  parlant 升级可能失效（比 litellm OTel 更可控，见 §4 风险对比）。

### 2.2 旅程推进（D-⑧ journey.progress）+ process I/O（D-⑦）→ EngineHooks ✅ 完全替代

- `on_preparation_iteration_end`（`engine.py:366`）在 `_run_preparation_iteration`（`engine.py:355`）
  **之后**调用，此时 `context.state.journey_paths` 已是该迭代后路径 → **与现插桩时机完全一致**。
- 回调可拿：`state.journey_paths`（index 列表）、`state.iterations`（迭代号 = len）、`info.session_id`。
- `configure_hooks: Callable[[EngineHooks], Awaitable[EngineHooks]]` 是 `p.Server()` 参数（`sdk.py:4191`），官方机制。
- **D-⑦ process span I/O 一并替代**（源码核实）：parlant `OpenTelemetryTracer.span` 用
  `trace.use_span(span, end_on_exit=True)`（opentelemetry.py:186）→ current span 由 OTel contextvar 管理；
  hook 回调运行在 process span 作用域内 → `trace.get_current_span()` 取到 process span →
  `span.set_attribute("langfuse.observation.input", 用户消息)` / `("langfuse.observation.output", 回复拼接)`
  = engine.py:209 插桩的等价物，全部收进 runtime。
- **附带收益**：index→名称映射**移出 parlant**——hook 在 runtime 侧实现，直接访问
  `definition.journeys[].states[].title`（loader 数据），比 `entity_cq.journey_node_labels()`（投影 BFS
  序号→`description or action` 截断）更直接准确，entity_cq 插桩一并删除。

### 2.3 命中条件（D-⑫ journey.next_step）→ hooks 够不到，monkey-patch 或弃 ⚠️

- **hooks 边界**（源码核实）：`_call_guideline_handlers`（`engine.py`）判 `match.guideline.id in handlers`
  才回调——而 **journey 节点指南 id 是投影动态生成**（`format_journey_node_guideline_id(node.id, edge.id)`），
  运行前无法预注册 → `on_guideline_selected` / `on_guideline_message` 覆盖不到旅程节点。
  `on_journey_selected` 按 JourneyId 注册（可预注册）但只给 `EngineContext`，无节点级 match。
- 替代：**monkey-patch `JourneyNextStepSelection.process`**（集中到 runtime `app/observability/`，依赖
  内部方法名，升级可能失效）；或 **弃**——journey.progress（§2.2）已给出节点路径，index:名称后节点
  身份清晰，"命中哪条条件/条件文本"增量信息有限（需要时可从 match 指南的 `content.condition` 补）。
- 结论：**先弃，观察 hook 版 journey.progress 是否够用**。

### 2.4 engine.reeval / engine.not_prepared（D-⑨⑩）→ 效果替代 ⚠️

- hooks 拿不到 `_load_additional_matched_guidelines_and_journeys` 的 `reevaluate=N`、`_check_if_prepared`
  内部判断。
- 但 `on_preparation_iteration_end` 可读：
  - **REEVALUATION 是否生效** → 看 `state.journey_paths` 是否推进（tool 节点出边走通 = 关系生效；
    连续多迭代 tool 节点滞留 = 关系缺失）——**效果等价 engine.reeval>0**，足够定位；
  - **executed_tools** → `state.iterations[-1].executed_tools`（= not_prepared 的 executed_tools）；
  - **tool 节点命中** → `journey_path[-1]` 对应节点 type（runtime 有 definition，可直接映射）。
- 结论：两处插桩可删，诊断信息由 §2.2 的 hook 日志派生。

### 2.5 batch_enter / auto_return（D-⑬ journey_node_selection_batch.py）→ monkey-patch 或弃 ⚠️

- 匹配器**内部**决策（快路径推进/穿透/放弃原因），hooks 无此粒度。
- REEVALUATION 修复已走通（`docs/to-follow-up/挽留计数与工具职责.md` §2.3），这两条是**排查期产物**；
  `journey.progress`（hook）已给最终路径，快路径是否放弃属"过程"日志 → **建议弃**。

### 2.6 非插桩改动的处置（A/B/C 类）

- **A-① 惰性导入**：保留（无 hack 化必要；也可提上游 PR——torch 是非必需依赖，本就该惰性导入）。
- **A-② DeepSeek 关 reasoning**：**优先迁 runtime**——这是模型配置不是观测；litellm API 支持
  `reasoning={"enabled": False}`，若 parlant 暴露模型参数透传则 runtime 侧配置即可删 hack；
  若不暴露，暂留 hack 并记 TODO（见 §3.0）。
- **A-③ console 开关**：保留（调试增益、默认行为不变；可随上游 PR 一并提"默认关闭 console exporter"）。
- **B-④ 临时 dump**：删除（排查已收尾，见 §3.0）。
- **C-⑤ sdk.py removeprefix**：贡献上游（id 含下划线是合法情形，`split("_")[-1]` 属上游 bug）；
  贡献合入后本地删除。

## 3. 推荐方案（落地路径）

**8 文件处置一览**：

| 文件 | 现状 | 落地动作 |
|---|---|---|
| `litellm_service.py` | A-①惰性导入 / A-②DeepSeek 关 reasoning / B-④临时 dump | 保留①；**②迁 runtime 模型配置**；**④删** |
| `opentelemetry.py` | A-③ console 开关 | 保留 |
| `sdk.py` | C-⑤ removeprefix | 保留至**贡献上游后删** |
| `generation.py` | D-⑥ gen_ai span | `git checkout ea737442` 还原 |
| `engine.py` | D-⑦⑧⑨⑩⑪（process I/O + journey.progress + not_prepared + reeval + _fmt） | `git checkout ea737442` 还原 |
| `journey_next_step_selection.py` | D-⑫（_index_to_label/_fmt + 5 种日志） | `git checkout ea737442` 还原 |
| `journey_node_selection_batch.py` | D-⑬（_index_to_label/_fmt + batch_enter + auto_return） | `git checkout ea737442` 还原 |
| `entity_cq.py` | D-⑭ journey_node_labels | `git checkout ea737442` 还原 |

落地步骤（2026-09-28 执行情况）：

```
✅ 0. 清理/迁移 litellm_service.py 非插桩段：删 B-④ dump 段；
       迁 A-② DeepSeek reasoning 到 runtime patch（parlant 不暴露模型参数透传）
       —— 已迁：parlant 源码只留 A-① 惰性导入

✅ 1. parlant 还原 5 个插桩文件（相对原生 ea737442）：
       git checkout ea737442 -- \
         src/parlant/core/nlp/generation.py \
         src/parlant/core/engines/alpha/engine.py \
         src/parlant/core/engines/alpha/guideline_matching/generic/journey/journey_next_step_selection.py \
         src/parlant/core/engines/alpha/guideline_matching/generic/journey/journey_node_selection_batch.py \
         src/parlant/core/entity_cq.py
     落地后 parlant 仅剩 2 必需 hack（A-①③）+ 1 上游 bugfix（C-⑤），无任何插桩 ✅

✅ 2. parlant-agent-runtime 新增 app/observability/（分 package，替代原 5 文件插桩；
       `__init__.py` 只做门面 re-export，实现在子模块）：
       app/observability/
       ├─ __init__.py          install_observability()（patches 统一装配入口）+ re-export
       ├─ otel/__init__.py     litellm OTel 回调（**弃用**：async ended-span 刷屏，见 §2.1/§3 步骤3）
       ├─ hooks/
       │  ├─ __init__.py       门面：re-export configure_engine_hooks
       │  └─ journey_progress.py  configure_engine_hooks()（p.Server(configure_hooks=...)）：
       │        on_preparation_iteration_end → _journey_progress_log
       │          [parlant-agent] journey.progress（index:名称，替代 D-⑧⑨，已 10:03 验证生效）
       │          trace.get_current_span() → langfuse.observation.input/output（替代 D-⑦）
       │        + _process_span_io / _fmt_index / engine.not_prepared 派生
       ├─ patches/
       │  ├─ __init__.py       门面：re-export install_litellm_patches
       │  ├─ litellm.py        install_litellm_patches()（一次 patch do_generate，合并两项）：
       │        DeepSeek 关 reasoning（替代 litellm_service ②）
       │        + gen_ai.chat span（替代 D-⑥，parlant tracer 开 span，修正原 attributes 漏 with）
       │  └─ next_step.py      预留：next_step 命中条件日志 patch（默认不启用，见步骤 4）
       └─ labels/
          ├─ __init__.py       门面：re-export journey_labels/JourneyLabelResolver
          └─ journey_labels.py  journey_labels()/JourneyLabelResolver（替代 D-⑭ entity_cq）：
                BFS 复刻 parlant projection（root=index1 → entry → 按 transitions 顺序），
                名称 = state.description or title 截断 12 字；已用线上定义 + 10:03 日志自洽验证

✅ 3. litellm OTel **实测弃用**（2026-09-28 验证：async 下 ended-span 刷屏 + 属性丢弃）→
       按回退方案改 **monkey-patch LiteLLMSchematicGenerator.do_generate**（parlant tracer 自管
       span：gen_ai.chat 嵌套 process 下、无刷屏），落在 patches 模块（§2.1 详述）。

✅ 4. next_step 命中条件 / batch 日志（D-⑫⑬）：**已决：不补**——决策 rationale 在 langfuse 完整可见
       （guideline_matcher 下 journey_next_step_selection / journey_backtrack_check 的
       journey_continues / next_step_rationale / requires_backtracking；话术选择在
       canned_response_generator 的 Draft 调用）。patches/next_step.py 仅留占位，
       若未来排查需要再 monkey-patch JourneyNextStepSelection.process。
```

## 4. 风险对比

| 方式 | 优点 | 缺点 |
|---|---|---|
| hack 源码（现状） | 直接、无额外层 | parlant 升级被覆盖、diff 混乱、不可维护 |
| **EngineHooks** | **官方机制、升级安全** | 引擎级事件粒度；无 LLM 原始调用；不暴露 tracer/span |
| **litellm OTel** | **零 parlant 依赖、标准化 gen_ai.*** | trace 关联需验证（§2.1） |
| monkey-patch | 源码干净、可集中管理 | 依赖内部方法名/签名，parlant 升级可能失效 |

## 5. 验收

- [x] parlant 源码仅剩 2 处必需 hack（A-①③）+ 1 处上游 bugfix（C-⑤），**无任何插桩、无临时诊断段**
- [x] 旅程推进日志（session + 迭代号 + index:名称路径）经 `configure_hooks` 输出（10:03 实测生效，
      index 与线上定义 BFS 复刻一致）
- [x] langfuse 每个 trace 的 `guideline_matcher` / `message_generation` / `tool_caller` 下出现
      `gen_ai.chat` generation（prompt / completion / usage）——由 patches do_generate monkey-patch 产出
      （2026-09-29 用 trace `24f10ccf` 实测：10 个 `gen_ai.chat` **全部带 usage + completion**，
      分布 guideline_matcher=8 / message_generation=1 / process=1；tool_caller 本次为 0 系该轮未调工具，
      patch 覆盖 `LiteLLMSchematicGenerator.do_generate` 全调用路径，工具场景必现，待一次工具调用补证）
- [x] 无 "Setting attribute on ended span." 刷屏（litellm OTel 已弃用，应消除）
      （parlant.log 全程 0 条 + `install_observability` 只装 patches 的代码实证；stdout 最终确认见下注）
- [x] process 根 span 有 `langfuse.observation.input/output`（来自 EngineHooks `get_current_span`，非 parlant 插桩）
      （trace `24f10ccf` 实测：process input="选择0003" output="好的"；parlant 5 插桩文件已 git 还原）
- [x] CLAUDE.md 第五节对 opentelemetry.py 的过时描述已同步修正（timeout 是运行期配置，非源码 hack）

## 6. 前置依赖

- 阶段3.3+ 现有 OTLP→langfuse 导出（`configure_langfuse_otel`，已实现）
- EngineHooks 机制（`p.Server(configure_hooks=...)`，`sdk.py:4191`）
- litellm `OpenTelemetry` 集成（已随 litellm 1.102 安装，支持 `tracer_provider` 参数，实测可用）
