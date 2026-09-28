# 观测插桩"去 hack 化"改造方案（技术债）

> 状态：**待实施**（2026-09-28 基于最新代码重评，结论：**3 处核心插桩均可非 hack 替代**）。
> 背景：为排查旅程/LLM 问题，我们在**可编辑安装的 parlant 源码**里加了观测插桩（累计 4 文件 +
> 1 辅助方法）。本方案评估用 **litellm 原生 OTel / EngineHooks / monkey-patch** 替代，恢复 parlant
> 源码干净、升级安全。
> 依据：langfuse OTLP 摄入规则（`gen_ai.*` 属性→generation；`langfuse.observation.input/output`→span I/O）、
> Parlant EngineHooks（`src/parlant/core/engines/alpha/hooks.py`）、litellm 1.102 `OpenTelemetry` 集成
> （支持传 `tracer_provider`）。

---

## 1. 现状：parlant 源码插桩清单（2026-09-28 快照）

| 文件 | 插桩 | 目的 | 非 hack 方案 |
|---|---|---|---|
| `core/nlp/generation.py` | `[langfuse] gen_ai.chat` span（prompt/completion/usage） | LLM 调用输入输出进 langfuse | ✅ **litellm OTel 回调** |
| `core/engines/alpha/engine.py` | `journey.progress`（+iter，**index:名称**） | 旅程推进定位 | ✅ **EngineHooks** |
| `core/engines/alpha/engine.py` | `engine.reeval`（迭代2 重评估返回条数） | REEVALUATION 关系诊断 | ⚠️ 效果替代 |
| `core/engines/alpha/engine.py` | `engine.not_prepared`（executed_tools / tool_node_matched） | 未准备原因 | ⚠️ 从 iterations 推断 |
| `.../journey/journey_next_step_selection.py` | `journey.next_step`（命中条件→path，**index:名称**） | 分支选择定位 | ⚠️ monkey-patch 或弃 |
| `.../journey/journey_node_selection_batch.py` | `journey.batch_enter` / `auto_return` | tool 快路径决策/放弃原因 | ⚠️ monkey-patch 或弃 |
| `core/entity_cq.py` | `journey_node_labels()`（index→名称辅助） | 日志可读性 | ✅ 移出 parlant |

> **另留**：2 处**必需 hack**（非插桩，保留）：`litellm_service.py`（JinaAIEmbedder 惰性导入，torch 兼容）、
> `opentelemetry.py`（控制台导出开关 + HTTP 噪声采样）；1 处**上游 bugfix**（`sdk.py` 评估任务名解析，
> `split("_")[-1]`→`removeprefix`，id 含下划线启动必崩，应贡献上游）。
> `workspace/parlant` 是独立 git repo，插桩可 `git checkout` 还原。

## 2. 替代可行性矩阵（2026-09-28 基于源码逐条核实）

### 2.1 LLM I/O（gen_ai span）→ litellm OTel 回调 ✅ 零 parlant 改动

- litellm 1.102 自带 `OpenTelemetry` 集成，**`OpenTelemetry(tracer_provider=...)` 支持传 provider**
  （实测 `inspect.signature` 确认）→ 直接复用 parlant 全局 TracerProvider，无双 provider 冲突风险。
- 接入：runtime 在 p.Server 启动后 `opentelemetry.trace.get_tracer_provider()` 取 parlant 全局 provider →
  `otel = OpenTelemetry(tracer_provider=provider)` → `litellm.callbacks = [otel]`。
- 每次 LLM 调用自动发 `gen_ai.*` span（operation name / prompt / completion / usage）→ langfuse 渲染为 generation。
- **唯一不确定点**（文档 12 原标注）：litellm span 与 parlant `process` span 的 **trace 关联**——
  litellm 回调整合 callback 在 LLM 调用线程内取 current span context 建 parent。parlant 引擎跑在同一
  asyncio 单线程，理论上能关联；需小实验确认（§5.4 有验收项）。

### 2.2 旅程推进（journey.progress）→ EngineHooks ✅ 完全替代

- `on_preparation_iteration_end`（`engine.py:366`）在 `_run_preparation_iteration`（`engine.py:355`）
  **之后**调用，此时 `context.state.journey_paths` 已是该迭代后路径 → **与现插桩时机完全一致**。
- 回调可拿：`state.journey_paths`（index 列表）、`state.iterations`（迭代号 = len）、`info.session_id`。
- `configure_hooks: Callable[[EngineHooks], Awaitable[EngineHooks]]` 是 `p.Server()` 参数（`sdk.py:4191`），官方机制。
- **附带收益**：index→名称映射**移出 parlant**——hook 在 runtime 侧实现，直接访问
  `definition.journeys[].states[].title`（loader 数据），比 `entity_cq.journey_node_labels()`（投影 BFS
  序号→`description or action` 截断）更直接准确，entity_cq 插桩一并删除。

### 2.3 命中条件（journey.next_step）→ hooks 够不到，monkey-patch 或弃 ⚠️

- **hooks 边界**（源码核实）：`_call_guideline_handlers`（`engine.py`）判 `match.guideline.id in handlers`
  才回调——而 **journey 节点指南 id 是投影动态生成**（`format_journey_node_guideline_id(node.id, edge.id)`），
  运行前无法预注册 → `on_guideline_selected` / `on_guideline_message` 覆盖不到旅程节点。
  `on_journey_selected` 按 JourneyId 注册（可预注册）但只给 `EngineContext`，无节点级 match。
- 替代：**monkey-patch `JourneyNextStepSelection.process`**（集中到 runtime `app/observability/`，依赖
  内部方法名，升级可能失效）；或 **弃**——journey.progress（§2.2）已给出节点路径，index:名称后节点
  身份清晰，"命中哪条条件/条件文本"增量信息有限（需要时可从 match 指南的 `content.condition` 补）。
- 结论：**先弃，观察 hook 版 journey.progress 是否够用**。

### 2.4 engine.reeval / engine.not_prepared → 效果替代 ⚠️

- hooks 拿不到 `_load_additional_matched_guidelines_and_journeys` 的 `reevaluate=N`、`_check_if_prepared`
  内部判断。
- 但 `on_preparation_iteration_end` 可读：
  - **REEVALUATION 是否生效** → 看 `state.journey_paths` 是否推进（tool 节点出边走通 = 关系生效；
    连续多迭代 tool 节点滞留 = 关系缺失）——**效果等价 engine.reeval>0**，足够定位；
  - **executed_tools** → `state.iterations[-1].executed_tools`（= not_prepared 的 executed_tools）；
  - **tool 节点命中** → `journey_path[-1]` 对应节点 type（runtime 有 definition，可直接映射）。
- 结论：两处插桩可删，诊断信息由 §2.2 的 hook 日志派生。

### 2.5 batch_enter / auto_return（journey_node_selection_batch.py）→ monkey-patch 或弃 ⚠️

- 匹配器**内部**决策（快路径推进/穿透/放弃原因），hooks 无此粒度。
- REEVALUATION 修复已走通（`docs/to-follow-up/挽留计数与工具职责.md` §2.3），这两条是**排查期产物**；
  `journey.progress`（hook）已给最终路径，快路径是否放弃属"过程"日志 → **建议弃**。

## 3. 推荐方案（落地路径）

```
1. parlant 还原全部插桩（git checkout 以下 6 文件）：
     core/nlp/generation.py
     core/engines/alpha/engine.py
     .../journey/journey_next_step_selection.py
     .../journey/journey_node_selection_batch.py
     core/entity_cq.py
   保留：litellm_service.py / opentelemetry.py（2 必需 hack）+ sdk.py（上游 bugfix，贡献上游）

2. parlant-agent-runtime 新增 app/observability/，集中管理（不再散落 parlant 源码）：
   ├─ langfuse_otel.py   litellm OpenTelemetry 回调
   │     otel = OpenTelemetry(tracer_provider=trace.get_tracer_provider())
   │     litellm.callbacks = [otel]        # gen_ai.* span → langfuse generation
   ├─ hooks.py           configure_hooks(on_preparation_iteration_end=journey_progress_log)
   │     journey_progress_log(context, *):   # = 原 journey.progress
   │        session = context.info.session_id
   │        iter    = len(context.state.iterations)
   │        paths   = {jid: [fmt_idx(idx) for idx in path] for ...}   # index:名称
   └─ journey_labels.py  index→名称（读 definition title，替代 entity_cq.journey_node_labels）

3. 小实验验证 litellm OTel 与 parlant tracer 的 trace 关联（唯一不确定点）：
   若 span 断链 → 回退 monkey-patch BaseSchematicGenerator.generate（集中 observability 模块）

4. next_step 命中条件 / batch 日志：先弃，观察 hook 版 journey.progress 够不够用；
   不够再 monkey-patch JourneyNextStepSelection.process（集中模块）。
```

## 4. 风险对比

| 方式 | 优点 | 缺点 |
|---|---|---|
| hack 源码（现状） | 直接、无额外层 | parlant 升级被覆盖、diff 混乱、不可维护 |
| **EngineHooks** | **官方机制、升级安全** | 引擎级事件粒度；无 LLM 原始调用；不暴露 tracer/span |
| **litellm OTel** | **零 parlant 依赖、标准化 gen_ai.*** | trace 关联需验证（§2.1） |
| monkey-patch | 源码干净、可集中管理 | 依赖内部方法名/签名，parlant 升级可能失效 |

## 5. 验收

- [ ] parlant 源码仅剩 2 处必需 hack + 1 处上游 bugfix，**无任何插桩**
- [ ] langfuse 每个 trace 的 `guideline_matcher` / `message_generation` / `tool_caller` 下出现
      `gen_ai.chat` generation（prompt / completion / usage）
- [ ] 旅程推进日志（session + 迭代号 + index:名称路径）经 `configure_hooks` 输出，行为与现插桩一致
- [ ] litellm OTel span 与 parlant `process` span **同 trace**（嵌套正确），无重复/孤儿 trace

## 6. 前置依赖

- 阶段3.3+ 现有 OTLP→langfuse 导出（`configure_langfuse_otel`，已实现）
- EngineHooks 机制（`p.Server(configure_hooks=...)`，`sdk.py:4191`）
- litellm `OpenTelemetry` 集成（已随 litellm 1.102 安装，支持 `tracer_provider` 参数，实测可用）
