# 评估机制与 evaluation_cache 运维

> 自研机制深挖 + 运维手册。旅程为什么能"知道下一步去哪"、缓存怎么命中、什么时候会坏、坏了怎么修。
> 案例基于 2026-09-26 草稿敏感分支事故（残缺评估导致旅程跑偏）的完整排查实录。

## 一、评估是什么

Parlant 在实体（指南/旅程）进入引擎时，用 LLM 对实体内容做一次**一次性预分析**，产出"执行元数据"（评估结果）。运行时引擎不再反复分析文本，直接消费这些结论：

| 评估类型 | 产出 | 作用 |
|---|---|---|
| **指南评估** | `properties`：continuous / customer_dependent_action_data / agent_intention_condition / internal_action | 告诉引擎这条指南"怎么执行"：是否持续型、动作是否依赖客户数据、是否意图型、是否内部静默动作 → 决定给它跑哪些匹配组件 |
| **旅程评估** | `node_properties`（含每个节点的 `journey_node.reachable_follow_ups` 可达分叉表）+ `edge_properties` | 告诉引擎旅程"怎么推进"：每个节点当前可达的后续分叉及**增强版条件守卫** → fork 选择的"菜单" |

`reachable_follow_ups` 是本篇核心：运行时旅程推进靠**指南匹配器**在可达分叉里选一条（`journey_next_step_selection.py`，其 prompt 会注入上下文变量，`builder.add_context_variables(...)` @649）。**菜单里没有的分支，模型永远选不到。**

## 二、为什么热加载必须后台补评估

SDK 的评估-应用流程（`_process_evaluations → _apply_single_evaluation`）只在 `p.Server().__aexit__` 执行一次，只覆盖"启动前已加载"的实体。我们的架构里实体是**热加载**的（发布推送、@draft 草稿实例）——等不到 `__aexit__` 的评估，节点缺 `reachable_follow_ups` → 运行时 fork 选择条件为空 → LLM 任何回答都是 `invalid condition id` → 路径 `[None]` → **旅程瘫痪**。

修复（`parlant-agent-runtime/app/services/agent_loader.py` `_evaluate_journeys_now`）：`load()` 装配完即 `asyncio.create_task` 后台逐旅程评估并应用。**必须后台化**：旅程评估是逐节点多次 LLM 调用（实测可达数分钟），阻塞会拖死 load/会话创建；评估完成前 fork 暂不可推进（entry/普通节点不受影响）；评估失败仅影响分叉推进，不阻断加载。完成时打印 `✅ 旅程评估完成：<title> (<journey_id>)`。

## 三、evaluation_cache.json 缓存机制

文件位置：`parlant-agent-runtime/parlant-data/evaluation_cache.json`（`PARLANT_HOME` 下）。顶层两个集合，集合名带版本号（跨 Parlant 版本隔离）：

```
guideline_evaluations_3.3.1   [ {id, creation_utc, version, properties}, ... ]
journey_evaluations_3.3.1     [ {id, creation_utc, version, node_properties, edge_properties}, ... ]
```

### 3.1 哈希算法（内容寻址，模型无关）

`sdk.py:689-713`，xxh3-128：

```
指南哈希 = xxh3(condition : action : tool_ids : journey_state_prop : properties_prop)
旅程哈希 = xxh3(journey.id : state_ids : transition_ids)
```

- **哈希输入里没有模型名/provider** → 换模型不重评估。
- **指南哈希没有任何实体 id/实例信息** → 跨实例、跨 agent 按文本共享；改文本 = 新哈希 = 新条目，旧条目变死数据（无害）。
- **旅程哈希只算结构 id** → 改变量默认值/描述不影响；改状态/转移（哪怕只改文本不改 id）**不影响**（id 不变）；增删状态/转移 → 哈希变 → 重评估。

### 3.2 缓存优先查找

`_evaluate_guideline` / `evaluate_journey`（`sdk.py:737` / `:824`）**先查缓存**：

```python
if cached := await collection.find_one({"id": {"$eq": _hash}}):
    return ...            # 命中：直接返回，零 LLM 调用
# miss：才走 BehavioralChangeEvaluator 调 LLM，完成后 insert_one 落缓存
```

重启后 published 实体若哈希全命中 → **启动评估零模型调用、秒过**（仅当定义结构变更过才重评估那部分）。

### 3.3 文件读写特性（运维关键）

`JSONFileDocumentDatabase`：**启动时（`__aenter__`）把整文件读进内存快照**；`insert_one` 改内存 + 整体回写；`__aexit__` 再回写。推论：

> **运行中直接编辑文件无效**——评估查的是内存快照，下次回写还会把你删的条目复活。
> **一切删除/修改必须在 runtime 停止状态下做。**

### 3.4 实例归属判定

条目**没有** instance 字段，靠 id 后缀隐式区分（后缀是哈希输入）：

```python
for e in d["journey_evaluations_3.3.1"]:
    keys = list(e["node_properties"].keys())
    print(e["id"][:8], "draft" if any("@" in k for k in keys) else "published")
```

- 旅程条目：`node_properties` 键名带 `@draft` → 草稿实例；无后缀 → 发布实例。（**别用根节点判断**——根节点是 SDK 每次加载随机生成的 id，不带后缀。）
- 指南条目：**无法也不需区分**（内容共享）。
- 未来多版本实例（`@2.0.2`）同理，后缀即身份。

### 3.5 已知瑕疵：并发双写

缓存库无唯一约束。两个评估同时 miss → 各跑各的 LLM → 各插一条（`id` 相同，`creation_utc` 差几秒）。`find_one` 取**文件里第一条**，即"采用哪次生成"是碰运气——若并发批次里混着一条残次品，可能被采用。当前无害（实测两条并发产物入口层都完整），日后可在评估侧加锁或插入去重。

## 四、故障模式

### 模式 A：评估完全缺失（有明确报错）

症状：日志刷 `invalid condition id N`，`journey.progress` 路径 `[None]`，旅程不推进。
原因：热加载实体没走后台补评估（老 bug，已修），或缓存文件被清/损坏。
处置：确认 `_evaluate_journeys_now` 生效 → 看启动日志有没有 `✅ 旅程评估完成` → 没有则查 `⚠️ 旅程评估失败`（多为当时模型故障，修好模型后删对应条目重评估）。

### 模式 B：评估残缺（静默，最阴险）★

**2026-09-26 事故实录**：草稿试跑"敏感身份"分支怎么都不对——不进转人工、直奔合同选择，且**无任何报错**。

排查路径：
1. `journey.progress` 日志显示草稿会话路径 `['2','5','6','8']`——能推进、无 `invalid condition id` → 排除模式 A。
2. `命中转移条件[N]=...` 插桩（`journey_next_step_selection.py`）显示 LLM 选了一条**前提全假**的条件（"isSensitive为false" 实际为 true；"用户已选择合同"实际没选）。
3. 读缓存条目 `node_properties[入口节点].journey_node.reachable_follow_ups` 对比发布/草稿两条：**发布 6 条分叉 vs 草稿只有 4 条**——缺失的正是 `isSensitive为true`（敏感分支）和 `orderNum为0` 两条，且 8/9 的 isBook 守卫写反。
4. 根因：评估内容是**评估时的模型生成的**。草稿那次评估（03:13）的模型输出不全，残次品被原样缓存——哈希只验结构，不验完整性。
5. 教训：**"路径能推进" ≠ "评估完整"。** 缺分支不报错，LLM 只能从菜单里选，菜单缺啥少啥。

## 五、运维 SOP

### 5.1 删除（残次/过期）缓存条目

```bash
# ① 停 runtime（必须！内存快照机制，运行中改=白改）
# ② 备份 + 删除
cd parlant-agent-runtime/parlant-data
cp evaluation_cache.json evaluation_cache.json.$(date +%Y%m%d%H%M%S).bak
python3 - <<'EOF'
import json
p = "evaluation_cache.json"
d = json.load(open(p))
d["journey_evaluations_3.3.1"] = [e for e in d["journey_evaluations_3.3.1"]
                                  if not e["id"].startswith("<条目id前缀>")]
json.dump(d, open(p, "w"), ensure_ascii=False, indent=1)
EOF
# ③ 启 runtime → published 评估秒过（全命中）→ 新建草稿会话触发后台重评估
```

### 5.2 触发重评估的方式

删条目后不会自动立即重跑——评估发生在**实例加载**时。触发方式（任选）：
- 新建一个该实例的会话（草稿会话创建即触发 `_ensure_draft_instance` → load → 后台评估）；
- 或重启 runtime（草稿实例在下次草稿会话时懒加载）。

注意 `@draft` 有**指纹变更感知**（server 比对草稿定义指纹），仅当草稿内容没变且实例已加载时才复用——所以"删缓存条目"必须配合"重新加载实例"才生效。

### 5.3 重评估后质检（不可省！模型生成不保证完整）

```bash
python3 - <<'EOF'
import json
d = json.load(open("evaluation_cache.json"))
e = [x for x in d["journey_evaluations_3.3.1"]
     if any("@" in k for k in x["node_properties"])][0]   # 取草稿条目
fus = e["node_properties"]["sta_4h4nEZ@draft"]["journey_node"]["reachable_follow_ups"]
paths = [f["path"] for f in fus]
assert len(fus) == 6, f"分叉只有 {len(fus)} 条"          # ① 数量 vs 定义转移数
assert ["3"] in paths, "缺敏感分支"                       # ② 关键分支在菜单里
# ③ 守卫方向抽查（按定义语义核对，如 8=已预约 需 isBook=true）
EOF
```

质检清单：① 入口分叉数 = 定义转移数；② 业务关键分支（如敏感身份）在菜单；③ 变量守卫方向抽查。**不核实就把新的残缺品当成修好了**——本次事故的教训。

### 5.4 何时全量重建

一般**不需要**删整个文件。仅当：大面积条目可疑（换模型前评估质量普遍差）且愿意承担全量重评估成本（逐实体 LLM 调用）时，才整体删除重建。

## 六、速查

| 事项 | 命令/位置 |
|---|---|
| 看启动评估是否完成 | runtime 日志 `✅ 旅程评估完成` / `⚠️ 旅程评估失败` |
| 看会话旅程路径 | 日志 `journey.progress session=<id> paths={...}`（插桩于 engine.py） |
| 看 fork 选了哪条 | 日志 `命中转移条件[N]=<条件文本>` |
| 读变量实体+存储值 | `curl --noproxy '*' -s http://127.0.0.1:8000/context-variables/<var_id>?include_values=true` |
| 缓存条目归属判定 | 见 §3.4 脚本 |
| 判实例变量是否写入 | `key_value_pairs` 里找 `agent:<实例id>` 键 |
