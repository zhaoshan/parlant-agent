# 评估机制与 evaluation_cache 运维

> 自研机制深挖 + 运维手册。旅程为什么能"知道下一步去哪"、缓存怎么命中、什么时候会坏、坏了怎么修。
> 案例基于 2026-09-26 草稿敏感分支事故（残缺评估导致旅程跑偏）+ 2026-09-27 哈希常量事故（SDK 缺陷导致评估永不刷新）的完整排查实录。

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

> **对照：为什么官方示例（healthcare.py 等）不需要这套。** 示例是"同步脚本"模式——`async with p.Server() as server:` 块内创建全部实体（`create_journey` / `create_guideline` 返回前即把实体注册进 `_journey_evaluations` / `_guideline_evaluations`，sdk.py:5459），块退出时 `Server.__aexit__` 自动 `_process_evaluations()` 一次性评估+应用（sdk.py:4325），且顺序是**先评估（4325）→ 再索引（4331）→ 最后才起 HTTP（4340）** → 分叉表在第一条请求前已就位，运行期 fork 直接读表。缓存对示例只是"首次 miss、之后命中"，结构固定、无多实例，§3.6 的哈希常量缺陷碰不到。本架构是**常驻服务 + 热加载**，实体创建发生在 `__aexit__` 早已过去之后，才需要自建这套补评估。

## 二点五、tool 节点的 REEVALUATION 关系（"分支依赖工具结果"的前提）★

**问题背景**（2026-09-28 走通 tool→fork）：tool 节点（如 counter）后接 fork 按工具结果路由，但 tool 节点滞留、fork 不推进——迭代2 就地吐一句，下一条消息才路由。

**机制**：迭代2 `_run_additional_preparation_iteration` 靠 `find_guidelines_that_need_reevaluation`（`entity_cq.py:390`）**反查「journey_node_tag → tool」的 REEVALUATION 关系**来重建旅程批处理、推进 tool 出边。若关系缺失 → 重评估返回 0 条（实测 `engine.reeval reevaluate=0`）→ 旅程批处理不跑 → tool 出边不推进。

**根因**：REEVALUATION 关系**只在 SDK 的 `_transition()`（fluent API，sdk.py:1520）里创建**；直接用 `journey._create_state` + `create_transition` 装配（我们的 `agent_loader.py`）会绕过它 → 关系缺失。

**修复（loader 必做）**：建 tool 状态时按 SDK 同款补建（`agent_loader.py _build_journey`）：
```python
await relationship_store.create_relationship(
    source=RelationshipEntity(id=_Tag.for_journey_node_id(state.id).id, kind=RelationshipEntityKind.TAG_ALL),
    target=RelationshipEntity(id=_tool_ref_to_id(t), kind=RelationshipEntityKind.TOOL),
    kind=RelationshipKind.REEVALUATION,
)
```
`create_relationship` 是 upsert（`core/relationships.py`），reload 幂等。**任何"分支依赖工具结果"的旅程都依赖这条关系，勿省略。**

**与评估的关系**：关系不在旅程哈希（`journey.id : state_ids : edge_ids`）里——补建关系**不触发重评估**、不改哈希；修后 `reevaluate=32`（全部旅程节点投影），迭代2 fork 正常路由（`next_step current=10 命中条件[2] -> path=['12','9']`）。

**诊断**：看 `[parlant-agent] engine.reeval session=... reevaluate=N`——修复前 0、修复后 = 旅程节点数。详见 `docs/to-follow-up/挽留计数与工具职责.md` §2.3。

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
- **旅程哈希只算结构 id** → 改变量默认值/描述不影响；改状态 action 文本（不改 id）**不影响**（哈希不变 → 命中旧分叉表，如需刷新见 §5.1）；改转移**条件文本**会变（条件参与边 id 生成，见下）；增删状态/转移 → 哈希变 → 重评估。

**旅程哈希的三类输入**（v3.3.1 实际拼接，`journey.id : state_ids : edge_ids`）：

- **state_ids**：定义层状态 id（`sta_4h4nEZ@draft` 等，带实例后缀）；只有**显式传入 `id=` 的实体**才在哈希里——SDK 随机生成 id 的实体（指南/术语/变量/话术）不在。
- **edge_ids**：`IdGenerator.generate(xxh3_checksum(f"{journey_id}{source}{target}{condition}"))`（journeys.py:1503）——**条件文本参与边 id**，改转移条件即改哈希；确定性生成，checksum 不重复时 count=1 恒定。
- **根节点 id**：`IdGenerator.generate(f"{journey_id}root")`（**RAW 字符串直接进生成器，不再预哈希**；`@draft` 后缀在其中）→ 根节点 id 随 journey.id 变，**不能拿根节点判实例归属**（§3.4）。
- **IdGenerator 计数副作用**（common.py:163）：同一次运行内重复 checksum 会追加 `-N` → 边 id 可能带计数后缀；重启归零。追踪对账别依赖边 id 精确值。

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

### 3.6 旅程哈希缺陷：SDK 不填充 states/transitions → 哈希常量（2026-09-27 修复）★

**现象**：结构怎么改都不重评估；缓存里永远只有第一条评估，新分支静默缺失。

**根因**：`Journey.states` / `journey.transitions` 是 `create_journey` 初始化的 dataclass 字段（仅含根节点）；而 SDK 的 `_create_state` / `create_transition` **只写 store、不追加进这两个列表**。旅程哈希恰好用这两个列表拼 → **哈希只含根节点 → 每个旅程的哈希是常量** → 评估缓存永不过期。

```python
# 实测（12 状态草稿实例，列表里只有根节点一个 id）：
xxh3_128("jny_LuAwQZ@draft:PB6GqXLcEz:") == "7c14e07c"   # 常量
# 修复后（加载器补齐列表，哈希结构敏感）：
xxh3_128("jny_LuAwQZ@draft:sta_4h4nEZ@draft:...") == "4502f92e"
```

**修复**（`agent_loader.py::_build_journey`）：装配时手动补齐两个列表——

```python
cast(list, journey.states).append(state)                       # 每个 _create_state 之后
cast(list, journey.transitions).extend(created_transitions)    # 全部转移建完
```

**为何对两条评估路径都生效**：`create_journey` 返回前已把**同一个 journey 对象**注册进 `_journey_evaluations`（sdk.py:5459）；加载器 append 的是同一对象 → 启动后台评估（§二）与 SDK `__aexit__` 关停评估共用同一份填充后的列表 → 同一结构哈希 → `__aexit__` 命中加载器写入的缓存，**不会双倍调 LLM**。

**验证**（2026-09-27 实录）：修复后 publish（`919dfebf`）与 draft（`4502f92e`）双双 miss、各全量重评估一次（~4min）；draft 分叉表出现新分支 `sta_kQ3mZ9@draft`、`sta_N4xD0A` 分叉 4→5；缓存写入新条目（publish 13 节点 / draft 14 节点）。旧 `ff50c628`（publish）/`7c14e07c`（draft）成孤儿条目（无害）。新条目又出现 ×2 重复——即 §3.5 已知并发双写，`find_one` 取第一条，无害。

> ⚠️ **换哈希规则的一次性代价**：此修复改变的是"结构如何算指纹"，不是数据 → **修复后首次启动，publish 与 draft 都会 miss 一次**、各全量重评估（后台、不阻塞启动，但评估完成前 fork 推进不了）；之后新哈希命中缓存，恢复秒过。评估粒度是**整旅程 all-or-nothing**：任一状态/转移增删或条件改动 → 全量重评估；action 文本改动 → 哈希不变 → 命中旧分叉表（如需刷新删条目，§5.1）。

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

### 模式 C：评估永不刷新（哈希常量，静默）★★

**2026-09-27 事故实录**：草稿加了一个"拒绝预约转人工"状态，重新发起草稿会话后**路径依然不进新分支**；`[eval诊断]` 显示 `hash=7c14e07c cache命中预判=True 用时=0.0s`——结构变了却命中"首次评估"。

**与模式 B 的本质区别**：模式 B 是"评估内容残缺，但删条目/换模型后可重评估"；模式 C 是"**评估根本不刷新**"——即使每次评估都完整，旧结论也永远占着缓存位。模式 B 的 09-26 事故（草稿只有 4 条分叉）底层其实也叠加了模式 C：草稿哈希是常量，03:13 那次之后从未重评估过。

排查路径：
1. `[eval诊断]` 日志（agent_loader.py `_evaluate_journey` 插桩，可长期保留）：`cache命中预判=True 用时=0.0s` 且 `分叉数` 缺新状态 → 结构没进哈希。
2. 手工复算哈希（§3.1 / §3.6）：若 node_ids 只有根节点一个 → SDK 未填充列表。
3. 修好加载器后重算 → 新哈希 miss → 全量重评估 → `分叉数` 出现新分支（如 `sta_kQ3mZ9@draft: 1`）。

诊断插桩（`_evaluate_journey`，排查期加的，可长期保留）：

```python
logger.info(f"[eval诊断] 旅程评估开始 id={journey.id} hash={_hash[:8]} cache命中预判={cache_hit}")
logger.info(f"[eval诊断] 旅程评估完成 id={journey.id} 用时={dt:.1f}s 分叉数={fu_counts}")
```

质检补充：`分叉数` 字典应覆盖**定义层每个状态**（含新分支节点）；入口节点分叉数 ≥ 定义转移数；改条件后哈希应变、旧条目成孤儿。

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

### 5.5 草稿发布到 publish：必须重评估（草稿结果不可复用）★★

发布（取 draft 槽 → 热加载 publish 实例）会**触发 publish 旅程全量重评估一次**。原因：评估哈希输入（journey.id / 状态 id / 边 id）里 **`@draft` 后缀是哈希输入的一部分** → 草稿哈希（`4502f92e`）≠ publish 新哈希 → miss → 重新调 LLM；且即使哈希相同，`node_properties` 的 key 是带后缀节点 id，应用到 publish 旅程也对不上号。草稿与 publish 结构相同、LLM 评估内容等价，属设计上的"浪费"。

**当前行为**：发布热加载后，publish 旅程后台重评估 ~4min；期间 fork 推进不了（entry/普通节点不受影响）。不阻塞、不报错。**发布后要验证分叉，等日志 `✅ 旅程评估完成：... (jny_LuAwQZ)`（无 `@draft` 后缀）再测。**

**优化方向（阶段5 发布编排）**：发布时做**结果移植**——取草稿评估结果，把 `node_properties` 的 key 剥掉 `@draft` 后缀，写入 publish 哈希对应的缓存条目，publish 加载直接命中，省掉这 ~4min。当前可接受每次发布多等几分钟后台评估。

## 六、速查

| 事项 | 命令/位置 |
|---|---|
| 看启动评估是否完成 | runtime 日志 `✅ 旅程评估完成` / `⚠️ 旅程评估失败` |
| 看会话旅程路径 | 日志 `journey.progress session=<id> paths={...}`（插桩于 engine.py） |
| 看 fork 选了哪条 | 日志 `命中转移条件[N]=<条件文本>` |
| 读变量实体+存储值 | `curl --noproxy '*' -s http://127.0.0.1:8000/context-variables/<var_id>?include_values=true` |
| 查评估哈希/命中预判 | `[eval诊断]` 日志（agent_loader.py `_evaluate_journey` 插桩，见 §四 模式 C） |
| 手工复算旅程哈希 | runtime venv：`xxh3_128(f"{journey.id}:{node_ids}:{edge_ids}")`（§3.1） |
| 缓存条目归属判定 | 见 §3.4 脚本 |
| 判实例变量是否写入 | `key_value_pairs` 里找 `agent:<实例id>` 键 |
