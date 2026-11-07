# Parlant 升级平移指南

> **目的**：升级 parlant 版本（`workspace/parlant` fork）时，平移两类本地适配——
> ① fork 源码改动（3 文件）② parlant-agent-runtime 的 monkey-patch（4 个 install）。
> **当前基线**：v3.3.1 tag 之后的上游提交 `ea737442` + 单个本地适配提交 `cd7183a4`（+23/−9）。
> 本文档随每次升级更新基线版本号。

---

## 1. 改动总览

### 1.1 fork 源码改动（`workspace/parlant`，1 提交 3 文件）

| 文件 | 改动 | 性质 | 解决的问题 |
|---|---|---|---|
| `src/parlant/sdk.py` `_process_evaluations` | 任务名解析 `split("_")[-1]` → `removeprefix(f"{entity_type}_evaluation_")` | **正确性 bugfix**（评估链路） | 任务名 `journey_evaluation_{id}` 按 `_` 切分取末段，id 含下划线（如 `jny_LuAwQZ`/`jny_advisor`）被截断 → `read_journey/read_guideline` ItemNotFoundError → **启动崩溃**（09-23 老预加载架构 100% 触发）。零预加载后 `_process_evaluations` 遍历空表提前 return，**处于蛰伏状态**，但保留：任何 SDK 侧重新承担评估的路径都会再踩 |
| `src/parlant/adapters/tracing/opentelemetry.py` | console exporter 加 `PARLANT_OTEL_CONSOLE_EXPORTER=1` 开关（默认关） | 可观测行为开关 | 原实现每个 span 以 JSON 刷 stdout，生产不可用 |
| `src/parlant/adapters/nlp/litellm_service.py` | 顶部 `JinaAIEmbedder` 导入改为 fallback 路径内惰性导入 | 环境兼容 hack | JinaAIEmbedder 依赖 hugging_face→torch，顶部导入在无 torch 机器上模块加载即炸 |

### 1.2 runtime monkey-patch（`parlant-agent-runtime`，install 时装配）

> 包结构（2026-11 起按"对 SDK 的关系"分类）：**A 类=修订 SDK 内部 → `app/patches/`；B 类=官方扩展点/装配 → `app/extensions/`；C 类=纯工具 → `app/utils/`**。升级时只需重点核对 A 类。

| `app/patches/eval_model_split.py` | `LiteLLMService.get_schematic_generator` | 评估/对话模型分流：评估 schema 走 `EVAL_LITELLM_*`，api_key 经 `_KeyedClient` force-override | 中 |

| patch | 锚点（parlant 内部符号） | 防什么 | 升级风险 |
|---|---|---|---|
| `app/patches/atomic_json_file.py` | `JSONFileDocumentDatabase._save_data` / `_load_raw_data` | SDK 非原子写 + kill -9 → 缓存文件 0 字节 → 全量重评估 | 低（存储层稳定区） |
| `app/patches/journey_hash_stable.py` | `_CachedEvaluator._hash_journey_evaluation_request` | 随机 edge id 参与哈希 → 每次重启全量重评估 | **中**（sdk.py 活跃区） |
| `app/patches/do_generate.py` | `LiteLLMSchematicGenerator.do_generate` | DeepSeek 推理 token 耗尽预算 → 空 content 全挂；gen_ai.chat span | 中 |

| `app/core/evaluator.py`（非 setattr，但深依赖 SDK 私有 API；拆分自原 agent_loader） | `Server._evaluator` / `_apply_single_evaluation` / `_guideline_evaluations` / `_progress_for` | 零预加载后 loader 是唯一评估器（`_evaluate_journeys_now/_evaluate_guidelines_now`） | 中 |

> `agent_loader` 不属 setattr patch，升级时同样要核对 SDK 私有 API 签名（见 §4）。

---

## 2. 锚点断言机制（2026-11 落地）

**问题**：setattr 式 monkey-patch 在锚点改名后**静默失效**——方法挂在错误目标上永远不会被调用，行为退化无任何报错。

**机制**：`app/patches/patch_guard.py` 的 `assert_anchor()`，每个 `install_*()` 在 setattr 前校验锚点存在，**缺失即抛 `PatchAnchorMissing`、启动失败**（硬失败而非告警——若上游已修复对应问题，正确动作本来就是删除该 install 调用）。报错信息含 patch 名与处置指引。

**升级后第一信号**：runtime 启动报 `[patch-guard]` → 按 §4 对照表处置，不要绕过断言。

---

## 3. 升级 SOP

```bash
# ① 备份锚点（旧版本地适配永可对照）
cd /Users/zhaoshan/workspace/parlant
git tag v3.3.1-local cd7183a4

# ② 取上游新版（origin 已指向 emcie-co/parlant）
git fetch origin --tags

# ③ 新基线分支
git checkout -b local/v3.4 v3.4        # 或 origin/develop 的某个稳定提交

# ④ 平移本地适配：单提交 cherry-pick，冲突一次性暴露
git cherry-pick cd7183a4

# ⑤ 逐 hunk 处置（§4 对照表）→ push 到自己的远端

# ⑥ parlant-agent 侧
cd /Users/zhaoshan/workspace/parlant-agent/parlant-agent-runtime
uv sync                               # editable 源指向 ../parlant，随版本走
# 按 §5 回归清单验证
```

**冲突处理原则**：不强行套用旧 hunk——带着"这行解决什么问题"（§1.1 表格第四列）在新基线上重新实现。3 个改动每个仅 2~9 行，手工重打 < 1 小时。

---

## 4. 逐改动平移对照表

### 4.1 fork 源码

| 改动 | 升级时怎么做 | "上游已修"信号 |
|---|---|---|
| sdk.py 任务名解析 | 先查上游：`grep -n 'removeprefix\|split("_")\[-1\]' src/parlant/sdk.py`。已修 → 丢弃本地 hunk；未修 → 套用到新的 `_process_evaluations`（注意它可能不再被 `__aexit__` 调用——蛰伏状态解除时更需确认语义） | 上游任务名构造方式改变（task 改名/不再用名字传 id）→ bugfix 语义必须保留，找新 id 传递点 |
| otel console 开关 | 对齐上游新的 `TracerProvider` 装配段；上游若已加 env 开关 → 删本地改动用上游的 | `grep -n "ConsoleSpanExporter" src/parlant/adapters/tracing/opentelemetry.py` 已有条件包裹 |
| Jina 惰性导入 | 定位新版 fallback embedder 构造点，保持"torch 依赖只在 fallback 路径导入"；上游已惰性化 → 删 | `create_embedder` 内出现局部 import / 上游引入 embedder 注册表 |

### 4.2 runtime patch（锚点缺失时）

| patch 锚点缺失的含义 | 处置 |
|---|---|
| `_save_data`/`_load_raw_data` 不存在 | SDK 存储层重构：找新的持久化写入口重新实现原子写；若上游改原子写 → 删 patch |
| `_hash_journey_evaluation_request` 不存在 | 评估器重构：找新的旅程哈希入口重新实现稳定签名；若上游哈希已稳（不含随机 edge id）→ 删 patch |
| `do_generate` 不存在 | 生成器大改：对齐新版生成入口重写 `_patched_do_generate`（DeepSeek reasoning + gen_ai span 两项） |
| `get_schematic_generator` 不存在 | 生成器装配重构：同步 `eval_model_split` 补丁（EVAL 分支需照抄新装配逻辑）；同时核对 `LiteLLM_Default` 构造签名 |
| loader 深依赖的 `_evaluator`/`_apply_single_evaluation`/`_guideline_evaluations` 不存在 | 评估应用链路重构：**这是最高优先核对项**（零预加载后 loader 是唯一评估器，签名变了评估全停，eval-status 门禁会全部 failed） |

---

## 5. 回归清单（约 30 分钟）

- [ ] **补丁自检**：启动无 `[patch-guard]` 报错（§2）；日志出现 `[json-file] 已安装原子写 patch`、`[journey-hash] 已安装稳定结构签名 patch`
- [ ] **启动形态**：零预加载——秒 ready → `✅ 后台加载 published agents 完成`
- [ ] **评估链路**：清 `evaluation_cache.json` + SiliconFlow 配置 → 全量评估一轮 → `eval_quality` 无 ⚠️ 幻觉告警 → `GET /internal/agents/{id}/eval-status` ready=true
- [ ] **对话链路**：模拟对话过 fork（投顾节点 3 推进到测评/推荐）；SSE 流式不断
- [ ] **观测**：langfuse 链路树完整、`gen_ai.chat` generation 在、DeepSeek 模型无 reasoning 污染
- [ ] **类型检查**：`cd parlant-agent-web && ./node_modules/.bin/tsc --noEmit`

---

## 6. 降低长期成本的路线

1. **上游化 PR 优先级**（emcie-co/parlant）：sdk.py 任务名 bugfix（真 bug，几乎必被采纳）> otel console 开关 > Jina 惰性导入。合并后 fork delta 从 3 文件缩到 1，升级平移 ≈ 处理一个 hunk。
2. **sdk bugfix 无法 runtime 化**（patch 点在长方法内部、不干净；且 id 下划线风格不可控）——上游化是它的唯一出路，优先推。
3. Jina 惰性导入也无法 runtime 规避（import 即炸）——fork 或上游修二选一，同样值得提 PR。
4. 若上游采纳 2/3 两项，fork 仅剩 Jina 一个文件时，可考虑进一步：在 parlant-agent 构建期用 `sitecustomize`/`import hook` 延迟加载规避，实现 fork 归零（升级 = 换版本号）——届时再评估。
