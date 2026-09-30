# 智能投顾 Demo Agent · 实现说明与演示脚本

> 对应 `docs/05-sample-agents/智能投顾Agent需求.md`（需求文档）的实现落地说明。
> 平台能力：remote 远程服务工具（通用 HTTP 工具内核）为本次新增，详见
> `docs/05-sample-agents/remote-http-tools.md`。

## 一、组件落地情况

| 需求组件 | 交付位置 | 说明 |
|---|---|---|
| 三方服务应用 | `invest-advisor-demo/` | 独立 FastAPI，文件存储（JSON），6 接口 |
| 6 个业务工具 | schema `tools`（source=remote） | 基于平台通用 HTTP 工具内核声明 |
| Journey「标准投顾流程」 | schema `journeys` | 13 状态（chat/tool 混合，含回退分支；入口档案校验 sta_profile_check + 终止 sta_notfound） |
| Guidelines（7 条） | schema `guidelines` | 合规门控用 DEPENDENCY + 数值优先级 + FLUID 话术落地 |
| Observations（8 个） | schema `observations` | 感知对话状态，作关系门控目标 |
| Relationships（10 条） | schema `relationships` | 3 DEPENDENCY + 7 PRIORITY |
| Context Variables（5 个） | schema `variables` | 关联 `get_customer_profile` + freshness 自动刷新 |
| Glossary（6 术语） | schema `glossary` | 术语知识层 |
| Canned Responses（5 条） | schema `canned_responses` | 合规话术 |

schema 文件：`parlant-agent-runtime/examples/inv-advisor-demo.json`（单一事实源，
可经 web「导入 JSON」或 server 定义层加载）。

## 二、启动顺序

```bash
# 1. 三方服务（模拟后端，文件存储）
cd invest-advisor-demo && uv sync && .venv/bin/python -m app.main   # :8300

# 2. runtime（需含 remote 工具内核的新代码，重启后生效）
cd parlant-agent-runtime && .venv/bin/python -m app.main            # :8000/8818

# 3. server（BFF）+ web 已就绪后，导入 schema：
#    web 首页「导入 JSON」粘贴 examples/inv-advisor-demo.json → 存草稿 → 构建页 → 发布
```

> ⚠️ runtime 进程需在 http_tools.py / agent_loader.py 改动后**重启**，否则 remote
> 工具无法解析（旧代码 resolve_tool 只认内置工具）。

## 三、演示场景脚本（需求 §5）

### 场景 1：普通客户新咨询
```
客户：我想投资理财。
Agent：问候，询问投资目标，引导风险测评（触发 Journey sta_A → sta_B）。
客户：（风险测评自报）我是稳健型，C2。
Agent：调用 assess_risk 提交 C2 → 展示风险等级（sta_C）→ 调用 get_products 查询适配产品（sta_D）。
Agent：推荐债券基金/银行理财（sta_E），进行风险揭示（sta_F，rsp_risk_disclosure）。
客户：确认购买。
Agent：调用 place_order 下单（sta_H）→ 提供确认号（sta_I）。
```

### 场景 2：VIP 专业客户
```
客户：我是 VIP，想配置一些高收益产品。
触发 obs_vip_customer / obs_senior_customer。
Agent：查询适配产品（vip 标签 + 风险等级门控）→ 推荐混合型产品 + 深度分析（gdl_vip_offer）。
客户：（犹豫）我再想想。
触发 obs_customer_hesitant → 关系 rel_hesitant_prio_products 压制 gdl_high_return，
      Journey 走 sta_J 处理犹豫 → 可回退说明（tr_J_E）或转人工（tr_J_K）。
```

### 场景 3：合规拦截
```
客户：直接推荐个高收益股票。
Agent：gdl_risk_first（priority 100）激活 → 未测评则 rsp_risk_not_assessed 拦截，
      引导先完成风险测评；测评后 gdl_risk_match 确保不推荐超风险产品。
```

### 场景 4：术语解释与变量协同
```
客户：给我推荐一个收益高的产品。
触发 obs_asks_specific_stock 或高收益需求 → 加载 risk_level 变量（get_customer_profile 刷新）。
gdl_risk_first / gdl_risk_match 按变量值合规拦截：
若 risk_level=C2 而客户要高收益 → rsp_reject_high_risk 拒绝并引导适配产品；
同时 Glossary 术语（适当性管理）让 Agent 用合规定义解释。
```

## 四、验收对照（需求 §6）

- [x] 三方服务可独立启动，6 API 全部可用（`curl` 实测）
- [x] schema 通过 web 导入校验器（0 issues），loader 端到端装配通过
- [x] 未完成测评不推荐：`gdl_risk_first`（priority 100）+ `gdl_high_return`
      `dependency obs_risk_assessed` 双重门控
- [x] 不超风险等级推荐：`gdl_risk_match` + `gdl_high_return`
      `dependency obs_risk_assessed` + `dependency obs_senior_customer`
- [x] Observations/Relationships 装配生效（loader 实测 10 条，0 跳过）
- [x] Context Variables 正确加载并刷新（变量绑定 `get_customer_profile` + freshness）
- [x] Glossary 术语入库（6 条）
- [x] 可视化平台展示：构建页工具/旅程/指南/变量/术语模块均可编辑展示
- [x] **场景 1 + 场景 3 真实对话 E2E 跑通（2026-09-29 实测，deepseek-v4.1-flash）**：
      完整链路 assess_risk → get_products → place_order（`ord_0001` 落库 demo
      `orders.json`），合规拦截（C2 客户要高收益股票 → 适当性管理拒绝）。

## 四·附、E2E 实测踩坑记录（2026-09-29，重要设计约束）

真机对话验证中发现两个引擎级约束，直接影响 schema 设计：

1. **旅程 priority 必须 ≥ 匹配的最高数值优先级指南**。引擎
   `RelationalResolver.find_highest_priority_entities` **只保留最高优先级实体**，
   其余一律丢弃。本 schema `gdl_risk_first`=100，若旅程 priority=0，则任何"投资
   咨询"轮次旅程与 trigger 指南被整体丢弃（`matched_journeys=[]`、旅程永不激活）。
   **修复：`jny_advisor` priority=100**（与最高指南持平，不高不低——高于 100 会把
   合规指南压掉）。验证：journey priority=0 时 `journeys=[]`；=100 后
   `journeys=['jny_advisor'] jstates=['sta_A'] journey_paths=[...]`。
2. **composition_mode=strict 是 footgun（多迭代引擎下）**。strict 强制 draft 匹配
   canned response，不匹配即丢弃 draft → 兜底 "Not sure I understand"。触发场景：
   - 宽条件合规指南（`gdl_risk_first` 原条件"客户请求投资建议"）在测评轮仍匹配
     （模型判定"自报 C2 ≠ 正式测评完成"），但 draft（"已完成测评"）与
     `rsp_risk_not_assessed` 矛盾 → fallback。
   - **修复**：全部指南 `composition_mode: fluid`；合规靠 action 指令 + canned
     response 检索渲染（能匹配就用话术、不匹配就用 draft，永不兜底失败）。
     `gdl_risk_first`/`gdl_risk_match` 条件同时收窄到违规场景（"尚未测评" / "要求
     超风险等级产品"），保证门控只在需要时激活。
   - 另：`rsp_risk_not_assessed` 实测在 fluid 模式下同样被检索渲染
     （turn 1 输出"在为您推荐产品之前，需要先完成风险测评"）。

## 四·补、平台能力增强（2026-09-30）

两个围绕本 Demo 落地的平台能力，非本 Agent 专属：

1. **server 定义层跨 Agent id 冲突预检（导入即报错）**：journey/state/guideline/
   observation 四类定义层 id 进引擎**全局**存储，多 Agent 必须全局唯一。`save()`
   导入时对其它每个 Agent 的最新定义提取同四类 id 做冲突比对，撞号抛 422 并列出
   冲突 id 与占用 Agent（加载器在发布时也有兜底拦截，这里把报错提前到导入）。
   实现：`parlant-agent-server/app/services/agents.py` `_check_cross_agent_id_conflicts`
   + repository `list_others_latest`。
2. **客户档案校验旅程（sta_profile_check → sta_notfound）**：旅程入口改为 tool 节点
   `sta_profile_check`（调 get_customer_profile）。查询 404（客户不在 demo 后端）→
   路由 `sta_notfound` 终止态，Agent 告知"未找到客户档案、无法服务、请确认身份"并
   结束会话；查询成功 → 路由原 `sta_A` 正常流程。契合"管理后台任意新用户会话"场景。
   实测：未知客户 → `GET /customer/{id}` 404 → `matched_journey_states=[sta_notfound]`；
   已知客户（cus_001）→ 200 → `sta_A` 问候正常，无回归。

## 五、已知限制与后续

- **沙箱/安全**（SSRF、任意 URL、鉴权）：通用 HTTP 工具当前不做防护，列为待办。
- **风险测评简化**：客户自报 C1~C5（需求允许），后续可接问卷式测评。
- **行情随机**：当前随机微调；后续可接 Brave Search 实时行情。
- **journey 回退**：sta_J → sta_E 的回退转移依赖旅程评估后的条件表，首次加载需
  等待后台评估完成（fork 推进）。
- **demo 数据文件**：`invest-advisor-demo/data/` 为运行时文件存储（客户/产品/订单/
  转人工），已加入 `.gitignore`；缺失时 app 按 SEED 常量自动重建。E2E 或演示后若
  客户状态被改（如已测评），删除 `data/customers.json` 重启即复位。
