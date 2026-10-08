# 16. M1 实施方案：API 加固 + 输入审核（含统一接入层/IAM 兼容设计）

> 状态：**方案已定，待实施**（2026-10-08）。
> 范围：`plan/阶段5-生产化` 的 **5.3 API 加固** + **5.1 输入审核**，作为"敢上线"的 M1 里程碑。
> 硬性约束：**为未来接入统一接入层（Gateway + IAM 权限体系）预留无缝切换的接缝（seam）**——依据
> `/Users/zhaoshan/workspace/unify-iam-server/20260825-Gateway-权限体系架构设计.md`。
> 不做的（避免过度设计）：用户/租户/角色的自有建表、完整 RBAC 管理台、数据策略 DSL——那些交给 IAM 层。

---

## 1. 现状基线（已核实，2026-10-08）

| 项 | 现状 | 风险 |
|---|---|---|
| server 鉴权 | 无 JWT/Bearer/Depends；`0.0.0.0:8081`；CORS `*` | 任何网络可达者都能建/删 Agent、读会话、发布 |
| runtime `/internal/*` | 无内部 token；`0.0.0.0:8000`（含 8818 工具口） | load/unload/变量覆盖可被直接调 |
| 输入审核 | 事件链路未带 moderation；无 Guard | 违规/注入输入直接进引擎 |
| 会话/配置写入身份 | `created_by="api"` 硬编码；session `user_id` 由 query 传 | 无真实身份溯源 |
| SSE | 事件流 `GET /sessions/{id}/events` 由 EventSource 消费 | EventSource 无法带 Authorization header |

---

## 2. 兼容性设计总则（重点）

IAM 文档的核心主张：**认证在网关、授权走统一 RBAC、业务应用只消费"已授权上下文"**（§4.2、§7.3）。
据此定下 M1 的接缝设计，确保未来接入网关时**路由代码零改动、只换 Provider**：

1. **不建自有用户/租户/角色表**。M1 只建"可插拔上下文解析层"（`app/authz/`），用 `AUTH_MODE` 选实现。
2. **`AuthorizationContext` 即未来网关交付物**：字段直接对齐 IAM §8.2
   （`userId / tenantId / membershipId / roles / permissions / attrs(dataAttributes)`）。
   业务代码只读它，不读任何硬编码身份。
3. **权限点目录 = 与 IAM RBAC 的对齐层**：路由 → 权限 code（`agent:publish` 等），
   code 命名与 IAM §9.1 的 `gateway_permission` 一致（AgentOperator→`agent:build/publish/test`）。
   未来网关把 roles→permissions 装配进令牌，server 按同一目录比对即可。
4. **JWT claims 契约固定**：`sub/userId/tenantId/membershipId/roles/permissions/attrs`；
   `issuer/audience/JWKS` 走配置——M1 自签发，未来指到网关公钥。
5. **默认拒绝**：无对应权限点 → 403（对齐 IAM §3.5 最小权限）。
6. **审计铺路**：鉴权决策、审核拦截、配置变更（save/publish/delete）落业务侧审计表，字段含
   userId/tenantId——未来可被网关统一消费（IAM §11.2）。

### 2.1 未来网关接入的两种形态（M1 都兼容）

- **形态 A（推荐演进）**：网关成为统一入口，web→网关→server；网关注入身份头或替换 JWT。
  server 的 Provider = `GatewayProvider`：校验网关签名 + 信任内网注入的上下文头。
- **形态 B**：web 仍直连 server，但令牌由网关签发 → server 校验网关 JWKS，CORS 收紧到 web 来源。

M1 按**形态 B 的最小契约**（JWT claims + JWKS 配置点 + Provider 接缝）实现，两条路都能接。

---

## 3. 设计骨架

### 3.1 `app/authz/` 包结构（server 侧新增）

```
parlant-agent-server/app/authz/
├── __init__.py
├── context.py        # AuthorizationContext dataclass（对齐 IAM §8.2）
├── provider.py       # AuthProvider 协议 + 按 AUTH_MODE 选实现
├── providers/
│   ├── dev.py        # AUTH_MODE=dev：自签发 JWT / bootstrap 上下文（开发用）
│   └── jwt.py        # AUTH_MODE=jwt：校验本地自签发 JWT（M1 默认生产形态）
│                      # （未来 gateway.py：校验网关 JWKS + 信任内网上下文头）
├── permissions.py    # 权限点目录：路由 → 所需 permission code
└── deps.py           # get_context() / require(code) 两个 FastAPI 依赖
```

### 3.2 `AuthorizationContext`（对齐 IAM §8.2）

```python
@dataclass(frozen=True)
class AuthorizationContext:
    user_id: str
    tenant_id: str          # M1 恒为默认工作区租户（如 "workspace"）
    membership_id: str | None = None
    roles: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()
    attrs: dict[str, list[str]] = field(default_factory=dict)  # dataAttributes
```

### 3.3 权限点目录（与 IAM `gateway_permission` 对齐）

| 路由 | 权限 code | IAM 角色示例 |
|---|---|---|
| GET /api/agents、versions | `agent:read` | Viewer / Analyst |
| POST /api/agents（建/存草稿）、journeys/layout | `agent:build` | AgentOperator |
| POST /api/agents/{id}/publish | `agent:publish` | AgentOperator |
| DELETE /api/agents/{id}/delete、/{id}、rollback | `agent:delete` | TenantAdmin |
| POST/GET /api/sessions、events | `session:read` / `session:send` | AgentOperator / Analyst |
| POST /api/customers | `customer:manage` | AgentOperator |
| GET /api/traces/* | `trace:read` | Analyst |
| GET /api/settings | `settings:read` | Viewer |
| /health | 公开 | — |

### 3.4 JWT claims 契约（固定，未来网关复用）

```jsonc
{
  "iss": "<M1: parlant-agent-server / 未来: 网关 issuer>",
  "aud": "parlant-agent-server",
  "sub": "<userId>",
  "tenantId": "workspace",
  "membershipId": null,
  "roles": ["AgentOperator"],
  "permissions": ["agent:read", "agent:build", "agent:publish", ...],
  "attrs": { }
}
```

---

## 4. 任务与文件级改动

### 4.1 [5.3-a] server 鉴权骨架（authz 包 + 依赖注入）

- 新增 `app/authz/*`（§3 结构）。
- `settings.py` 增：`auth_mode: str = "dev"`、`jwt_secret` / `jwt_issuer` / `jwt_audience`、
  `jwt_algorithm="HS256"`、`jwt_ttl_seconds=28800`、`internal_token`、`cors_allow_origins`（已有）收默认值。
- `main.py`：初始化 Provider（按 `auth_mode`），挂到 `app.state.auth_provider`；
  新增 `get_context` 全局依赖（缺省 401）——除 `/health`、`/docs`、dev 模式白名单外全量启用。
- dev 模式：`AUTH_MODE=dev` 时自动装配 bootstrap 管理员上下文（含全部权限），**不拖慢开发**；生产必为 `jwt`。
- 生效：`context.user_id` 回填 `AgentDefinitionService.save(created_by=context.user_id)`、session `user_id`（替换 query 传参的"演示用户"兜底）。

### 4.2 [5.3-b] 路由权限点接入

- 各 router 的目标函数加 `ctx: AuthorizationContext = Depends(require("agent:publish"))` 依赖。
- `require(code)`：`code in ctx.permissions` 否则 403；未认证 401。
- 变更点：`routers/agents.py`、`sessions.py`、`customers.py`、`traces.py`、`settings.py`（每函数 1 行依赖）。

### 4.3 [5.3-c] CORS 收紧

- `cors_allow_origins` 默认改白名单（如 `http://localhost:5173`、网关来源）；逗号分隔配置。
- 网关落地后：web 直连网关则 server CORS 保持收紧即可（web→网关→server 是服务间调用）。

### 4.4 [5.3-d] runtime `/internal/*` 服务间鉴权 + 绑定收紧

- runtime：`/internal/*` 挂 `X-Internal-Token` 校验依赖（`settings.internal_token`，无则拒绝）；host 默认改 `127.0.0.1`（内网 IP 走 env）；8818 同收紧。
- server `RuntimeClient` 全部请求（含 `runtime_info`、SSE 订阅）加 `X-Internal-Token` header（复用既有 `trust_env=False`）。
- **反向**：runtime→server 的 `GET /api/internal/published-agents`（启动拉取）同样加 `X-Internal-Token`，server 校验。
- 说明：这是**服务间信任**，与用户 IAM 正交；未来网关接入后 server 仍用它保护自己的内部端点。

### 4.5 [5.3-e] SSE 鉴权（EventSource 带不了 header）

- 事件流走 `GET /api/sessions/{id}/events`：dev 用短时 `?token=<jwt>`（JWT 是 ASCII，符合"query 传 ASCII"既有约定）；
  生产建议 HttpOnly cookie（登录时 Set-Cookie，SSE 同源自动携带）。实现先做 query token，cookie 留 seam（`TOKEN_TRANSPORT=cookie|query`）。

### 4.6 [5.3-f] 限流（可选，建议做登录/事件两个口）

- `slowapi`：`/api/sessions/{id}/events`、会话创建按 IP+user 限流；生产 `MODERATION` 与登录接入网关后由网关统一限流（M1 先自保）。

### 4.7 [5.1-a] 输入审核（Guard + moderation 透传 + 拒绝话术 + 审计）

- `settings.py` 增 `moderation_provider: str = "none"`（`none|llama_guard|lakera`）+ 阈值。
- 新 `app/services/moderation.py`：`moderate(session_id, text, ctx) -> Decision{pass, reason, score}`。
  - `llama_guard`（本地，推荐，免外网）：GGUF/transformers 二分类（safe/unsafe），低延迟。
  - `lakera`（云）：HTTP 调用，需 API key。
- 注入点：server 转发事件前（`RuntimeClient.post_event` 前置或在 sessions router 事件端点）对
  customer message 做检查；命中 → 返回预设拒绝话术（复用 canned response 机制）+ **不转发引擎** + 落审计。
- 透传兜底：转发时带 `?moderation=moderate`（Parlant 原生参数）双保险。
- 审计表（新 `audit_log`，见 4.8）：`session_id / user_id / tenant_id / action=moderation_block / detail(reason,score)`。

### 4.8 [5.1-b] 审计表（为 IAM §11.2 铺路，M1 种）

- MySQL 新表 `audit_log`：`id, ts, tenant_id, user_id, session_id, action, resource, detail_json, ip`。
- 埋点（M1）：鉴权 401/403、moderation_block、`save/publish/delete_agent/purge`（配置变更，谁/何时/改哪个组件）。
- 未来：网关统一审计时本表可迁/可被网关消费，字段预留 `tenant_id/user_id`。

---

## 5. IAM 兼容性核对表（对照《Gateway 权限体系架构设计》）

| IAM 设计点 | M1 落点 | 备注 |
|---|---|---|
| 认证与授权解耦（§3.2） | AuthProvider=认证，权限点目录=授权，两层分开 | ✓ |
| 应用只消费 AuthorizationContext（§4.2/§8.2） | `app/authz/context.py` 字段逐一对齐 | 未来网关直接产同构上下文 |
| 默认最小权限（§3.5） | 无权限点即 403 | ✓ |
| permission code（§9.1 `agent:publish` 等） | `permissions.py` 目录同命名 | 网关 roles→permissions 可直配 |
| 接口 RBAC 先行、数据策略后置（§7.3） | M1 只做接口 RBAC；`attrs` 字段预留数据策略入参 | 数据策略不实现（交给 IAM） |
| 网关统一接入（§4.1 Gateway） | JWT claims 契约 + `auth_mode` Provider seam | 形态 A/B 均可切换 |
| SSO/JIT/group 映射（§5.2/7.2） | **不实现**；由网关完成后把 roles/permissions 放进令牌 | 避免重复造轮子 |
| 租户隔离（§3.1/5.1） | `tenant_id` 进上下文，恒"workspace"；created_by/user_id 溯源 | 网关落地后按 tenantId 过滤即水到渠成 |
| 审计（§11.2） | 业务侧 `audit_log` 先种，含 tenant/user | 未来可被网关统一消费 |
| 逻辑分层、物理同库（§10.2） | 新增独立 `app/authz/` package 边界 | 对齐其迁移指引 |

---

## 6. 验收清单

- [ ] `AUTH_MODE=jwt` 下，无令牌访问 `/api/agents` 401；有令牌无权限点 403；有权限 200
- [ ] `AUTH_MODE=dev` 下全功能可用（开发不减速）
- [ ] runtime `/internal/*` 无 `X-Internal-Token` 返回 401；server→runtime 带 token 正常热加载/SSE
- [ ] runtime host 收紧后 8000/8818 不再对公网监听（`lsof -iTCP` 验证）
- [ ] CORS 收紧：非白名单来源被拦；web(5173) 正常
- [ ] SSE 事件流经 query token（dev）正常透传
- [ ] 违规输入命中 Guard → 预设拒绝话术 + 不转发引擎 + `audit_log` 落一条
- [ ] `save/publish/delete` 各落一条审计（含 userId）
- [ ] 全链路回归：首页创建→构建→发布→试跑→观测 带鉴权后仍通

---

## 7. 里程碑与风险

- **实施顺序**：4.1/4.2（鉴权骨架+路由）→ 4.3/4.4/4.6（CORS/token/限流）→ 4.5（SSE）→ 4.7/4.8（审核+审计）→ 回归。
- **风险**：
  - SSE/EventSource 鉴权是最大坑（无 header）——先 query token 再 cookie。
  - Llama Guard 本地推理需装依赖/模型体积；先 `moderate` 后视延迟上 `paranoid`（IAM/parlant 均建议分级）。
  - dev/jwt 双模式切换要避免漏保护路由（用全局依赖 + 显式白名单，别逐路由加）。
- **与阶段5 其余项的关系**：5.2 人工转交、5.4 看板都消费同一 `AuthorizationContext` 与审计表，M1 先打底。

---

## 8. 与 E2E-1 的融合开发范围（2026-10-08 补充）

> 与 `docs/03-production/17-网关接入首阶段最小实现-E2E-1范围.md` 融合后的 parlant-agent 侧范围。
> 结论：doc17 的「parlant-agent 最小交付」列几乎全部 ⊂ 本 doc 的 M1；唯一新增 = `gateway` Provider + web 端令牌接入。

### 8.1 Provider 最终形态：dev / jwt / gateway 三档

| Provider | 密钥来源 | 用途 | 启用 |
|---|---|---|---|
| `dev` | 无（自动装配 bootstrap 管理员上下文） | 本地开发不减速 | `AUTH_MODE=dev`（默认） |
| `jwt` | HS256 共享密钥 `jwt_secret`（本地自签发） | 未接 IAM 的独立部署生产默认 | `AUTH_MODE=jwt` |
| `gateway` | RS256 + JWKS（`jwt_jwks_url` 指向 IAM） | 接入 IAM 后生产形态（E2E-1） | `AUTH_MODE=gateway` |

> `jwt` 与 `gateway` 是同一验签器、不同密钥源；`gateway.py` 只需在 `jwt.py` 基础上换"取密钥"一步（JWKS 拉取 + kid 缓存）。三种形态共享 `permissions.py` 目录与 `AuthorizationContext`。

### 8.2 parlant-agent 侧推荐范围（三档优先级）

| 档 | 内容 | 对应 |
|---|---|---|
| 第一档 M1 主线 | 4.1 authz 骨架 + 4.2 路由权限点 + 4.4 内部 token + 4.3 CORS + 4.5 SSE | 独立可验收，不需 IAM |
| 第二档 E2E-1 增量 | `gateway.py` Provider + **web 端令牌接入最小件**（登录/填 token → Bearer 头 → SSE query token → 401 处理） | 等 IAM token/JWKS 就绪后并行联调 |
| 第三档 可选 | 4.8 审计（建议随 4.1 同步种）、4.7 输入审核、4.6 限流 | 生产加固收尾 |

### 8.3 落地顺序

```
阶段A（parlant-agent 独立可验收）     阶段B（E2E-1 联调）        阶段C（加固收尾）
4.1 authz骨架 → 4.2 路由权限点        gateway.py Provider        4.8 审计（若未种）
→ 4.4 内部token → 4.3 CORS           + web 令牌最小件            4.7 输入审核 → 4.6 限流
→ 4.5 SSE（可并行 IAM 侧 §5 开发）   ↔ IAM token/JWKS 联调
```

- 阶段A 不需 IAM，做完即满足本 doc §6 验收 1–6。
- 阶段B 与 IAM 侧（建表→seed→签 token→JWKS）并行；联调时 parlant-agent 只把 `AUTH_MODE` 切 `gateway` + 指向 IAM，**路由代码零改动**——验证接缝成立。
