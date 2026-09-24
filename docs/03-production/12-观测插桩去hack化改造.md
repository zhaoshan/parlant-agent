# 观测插桩"去 hack 化"改造方案（技术债，后续实施）

> 状态：**待实施**（2026-09-23 分析定稿，暂不改动）。背景：为排查旅程/LLM 问题，我们在
> **可编辑安装的 parlant 源码**里加了 3 处观测插桩（见 §1）。本方案评估用 litellm 原生 OTel /
> EngineHooks / monkey-patch 替代，恢复 parlant 源码干净、升级安全。
> 依据：langfuse OTLP 摄入规则（带 `gen_ai.*` 属性→generation；`langfuse.observation.input/output`→span I/O）、
> Parlant EngineHooks（src/parlant/core/engines/alpha/hooks.py）、litellm OTel 回调。

---

## 1. 现状：直接 hack 了 parlant 源码的 3 处插桩

| 文件 | 插桩 | 目的 |
|---|---|---|
| `src/parlant/core/nlp/generation.py` | `BaseSchematicGenerator.generate` 包 `gen_ai.chat` span（prompt/completion/usage） | LLM 调用输入输出进 langfuse |
| `src/parlant/core/engines/alpha/engine.py` | `journey.progress` 日志 + `process` span 输入/输出 | 旅程推进定位 |
| `src/parlant/core/engines/alpha/guideline_matching/generic/journey/journey_next_step_selection.py` | 命中转移条件日志 | 分支选择定位 |

> 另有 2 处**必需** hack（非插桩，保留）：`litellm_service.py`（JinaAIEmbedder 惰性导入，torch 兼容）、
> `opentelemetry.py`（控制台导出开关 + HTTP 噪声采样）。`workspace/parlant` 是 git repo，3 处插桩可 `git checkout` 还原。
>
> **另有 1 处上游 bug 修复**（非插桩，应贡献上游）：`sdk.py` `_process_evaluations` 评估任务名
> `f"{entity_type}_evaluation_{entity_id}"` 用 `split("_")[-1]` 解析 id——id 含下划线（如 `jny_LuAwQZ`）时
> 被截断 → `read_journey` ItemNotFoundError → **启动期必崩**。已改 `removeprefix(f"{entity_type}_evaluation_")`。
> 随旅程显式 id（loader 传 `id=journey_def.id`）引入而触发，未修前任何带下划线的旅程/指南 id 都会崩启动。

## 2. 替代方案可行性矩阵

| 目标 | EngineHooks | monkey-patch | 更优方案 | 结论 |
|---|---|---|---|---|
| LLM 输入输出 (gen_ai span) | ❌ 无 generation 层 hook | ✅ patch `BaseSchematicGenerator.generate` | ✅✅ **litellm OTel 回调** | **litellm OTel（零 parlant 改动）** |
| 旅程推进日志 | ✅ `on_preparation_iteration_end`（`EngineContext.state.journey_paths`+`info.session_id`） | ✅ patch `_list_journey_paths` | — | **hooks（官方机制）** |
| 命中转移条件日志 | ❌ hooks 够不到 matching batch 内部 | ✅ patch `JourneyNextStepSelection.process` | journey_paths 已能定位节点 | **可弃**（信息冗余） |
| process span 输入输出 | ❌ hooks 不暴露 tracer/span 设属性 | ⚠️ 脆弱（要复刻 span 结构） | gen_ai 已给各阶段 LLM I/O | **可弃**（冗余） |

**hooks 边界**：EngineHooks 是**引擎级事件**（on_preparing / on_preparation_iteration_end / on_message_generated /
on_journey_selected / on_guideline_message 等），**没有"原始 LLM 调用"层级**，也**不暴露 tracer/span**。
→ raw prompt/completion 只能靠 litellm OTel 或猴补丁；span 属性写入只能靠源码或猴补丁。

## 3. 推荐方案

```
1. 还原 3 处插桩源码：git checkout src/parlant/core/nlp/generation.py \
      src/parlant/core/engines/alpha/engine.py \
      src/parlant/core/engines/alpha/guideline_matching/generic/journey/journey_next_step_selection.py
   （保留 litellm_service.py / opentelemetry.py 两个必需 hack）
2. parlant-agent-runtime 新增 app/observability/ 模块，集中管理：
   ├─ litellm OTel 回调注册（LLM 输入输出）
   │    litellm.callbacks += [OpenTelemetry(...)]  → 每次 LLM 调用发 gen_ai.* span → langfuse generation
   └─ configure_hooks: on_preparation_iteration_end → 旅程推进日志（session + journey_paths）
3. 小实验验证：litellm OTel 回调与 parlant 全局 TracerProvider 的协同
   （provider 就绪时机 / 双 provider 冲突——唯一不确定点）
   若冲突 → 回退用 monkey-patch BaseSchematicGenerator.generate（集中在一个 observability 模块）
```

## 4. 风险对比

| 方式 | 优点 | 缺点 |
|---|---|---|
| hack 源码 | 直接、无额外层 | parlant 升级被覆盖、diff 混乱、不可维护 |
| EngineHooks | 官方机制、升级安全 | 只覆盖引擎级事件；无 LLM 原始调用；不暴露 span |
| monkey-patch | 源码干净、可集中管理 | 依赖内部方法名/签名，parlant 升级可能失效 |
| litellm OTel | 零 parlant 依赖、标准化 gen_ai.* | 需验证与 parlant TracerProvider 协同 |

## 5. 验收

- [ ] parlant 源码仅剩 2 处必需 hack（litellm_service / opentelemetry），无插桩
- [ ] langfuse 每个 trace 的 guideline_matcher / message_generation / tool_caller 下出现 `gen_ai.chat` generation（prompt/completion/usage）
- [ ] 旅程推进日志（session + 节点路径）经 configure_hooks 输出，行为与现插桩一致
- [ ] litellm OTel 与 parlant tracer 协同无冲突（trace 结构、span 嵌套正常）

## 6. 前置依赖

- 阶段3.3+ 现有 OTLP → langfuse 导出（configure_langfuse_otel）
- EngineHooks 机制（`p.Server(configure_hooks=...)`）
- litellm `integration/opentelemetry`（已随 litellm 安装）
