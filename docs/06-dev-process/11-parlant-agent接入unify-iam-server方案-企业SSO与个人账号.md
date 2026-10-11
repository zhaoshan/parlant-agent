# 11. parlant-agent 接入 unify-iam-server 方案：企业 SSO + 个人账号（极简登录页先行，P3 收敛 IAM）

> 状态：**方案定稿，parlant 侧代码已落地（2026-10-09）**；IAM 侧企业 SSO/本地账号就绪，个人账号（PLATFORM）待补配。
> 依据：unify-iam-server `docs/01-总体设计与功能模块拆分` / `docs/03-E2E2-企业SSO`（含附录 A）；本仓库 M1 鉴权接缝（`app/authz/`）；`10-网关接入首阶段最小实现-E2E-1范围`。
> 决策：**先在 parlant 加极简登录页跑通「企业账号 + 个人账号 + 本地账号」双账号；P3 再把 hosted 登录页收敛到 IAM（login hub）**，业务前端只留「去登录」跳转。
> 核心承诺：**parlant 路由代码零改动**，仅换认证来源与登录入口。

> **落地记录（2026-10-09）**：§4 已实现——server `settings.iam_sso_base`、`GET /api/auth/sso/authorize`（302 IAM）、受保护 `GET /api/me`（新 me_router，`Depends(get_context)`，不入 /api/auth 免认证前缀）；web Login.tsx 三入口（企业 SSO / 本地表单 / 粘贴）+ SSO 回跳收 token（setAuth + replaceState 清 query + navigate）+ 个人按钮默认隐藏（`VITE_IAM_SHOW_PERSONAL=1` 开启）；index.html `no-referrer`。进程内已验：sso/authorize→302 IAM、/api/me 无 token→401、带 IAM token→200（u-1000/tenant-org-a/9 权限）。server 重启后生效。

> **2026-10-11 更新（实施改为形态 B：登录页收归 IAM hub）**：perlant web **删除登录页**（Login.tsx/RequireAuth 移除），改由 `AuthBootstrap` 启动分流——`GET /api/auth/mode`（server 公开）返回模式：`dev` → 写占位会话**免登录直进**；`gateway` → 跳 IAM hub（`settings.iam_hub_base`，如 unify-iam-web :5174）登录，hub 回跳 `?access_token` 由 AuthBootstrap 收。**jwt 模式（HS256 本地自签发）随登录页收归而淘汰**（无入口发/取 token），`JwtProvider`/`JWT_SECRET`/`token_generator.py` 一并删除，AUTH_MODE 收敛为 `dev | gateway` 两档（doc09 §8.1）。`GET /api/auth/mode` 与 hub 回跳收 token 已落地；本节下方 §4.4 三入口登录页为收敛前的方案记录。

---

## 1. 目标（一句话）

**parlant web 提供一个极简登录页，同时支持：企业账号（Keycloak SSO）、个人账号（Google/微软，平台级 IdP）、本地账号（IAM 密码），全部经 IAM 签发同一套 RS256 JWT（aud=parlant-agent-server）→ parlant `GatewayProvider` 验签生效（401/403/200 正确）。**

## 2. 现状基线

### 2.1 parlant-agent 已有（M1/P1，路由零改动）
| 件 | 现状 |
|---|---|
| `GatewayProvider` | `app/authz/providers/gateway.py`：PyJWKClient 拉 IAM JWKS、RS256 验签、iss/aud/exp 按配置校验 |
| 鉴权中间件 | `AuthzMiddleware` 全局保护 `/api/*`；白名单 `/health`、`/docs`、`/api/auth` |
| 登录 BFF | `routers/auth.py` `POST /api/auth/login` 转发 IAM `/api/v1/auth/token`（本地密码） |
| Web 登录页 | ~~`Login.tsx` 三入口~~（2026-10-11 已删）；`AuthBootstrap` 启动分流（dev 直进 / gateway 跳 IAM hub）+ `store/auth.ts` `setAuth`/`userFromToken`/`devSession` |
| SSE 令牌 | `?access_token=` query 传输（gateway 兼容） |

### 2.2 unify-iam-server 已有
| 能力 | 端点 / 契约 |
|---|---|
| 本地密码登录 | `POST /api/v1/auth/token` → `{access_token,...}`；aud=`parlant-agent-server` |
| 企业 SSO（OIDC） | `GET /api/v1/auth/oidc/authorize?tenant_id=tenant-org-a` → Keycloak → `.../callback` → 302 回前端带 token |
| JWKS | `GET /.well-known/jwks.json`（kid=iam-key-1，RS256） |
| issuer | `https://www.identityfabric.com`（现配置） |

---

## 3. 双账号模型与登录链路

- **企业账号**：parlant 按钮 → IAM `authorize?tenant_id=tenant-org-a`（租户级 IdP `kc-org-a`=Keycloak）→ 域名路由进组织租户 + group→role（AgentOperator）。
- **个人账号**：parlant 按钮 → IAM `authorize?tenant_id=PLATFORM`（**平台级 IdP**：Google External / 微软 MSA）→ JIT 建 **PERSONAL 租户** + Owner。
- **本地账号**：IAM `POST /api/v1/auth/token`（现有 BFF）。
- 三者最终都产出**同一套 claims 同构的 JWT**，parlant 侧无差别。

> 个人账号按钮的前提：**IAM 侧需先有 `tenant_id='PLATFORM'` 的 IdP 配置**（Google External 或 Microsoft MSA，docs/03 §10 / §6）。当前只有企业 Keycloak 配置——所以**先上「企业 SSO + 本地账号」两个入口跑通，个人账号入口在 IAM 补配 PLATFORM 后立即可用**（同一按钮、同一代码路径）。

### 3.1 个人账号关键澄清：共享 PLATFORM IdP ≠ 每用户一个租户（两层解耦）

「所有个人账号共用**一个平台级 IdP**」与「**每个个人账号一个 PERSONAL 租户**」是两层、互不冲突：

| 层 | 是什么 | 谁来定 | 配置 |
|---|---|---|---|
| **认证（Authentication）** | **共享**的 PLATFORM IdP（一个 Google External / 微软 MSA OAuth 客户端） | `gateway_tenant_idp_config` 一行 `tenant_id='PLATFORM'` | **有配置**（这一行） |
| **租户归属（Provisioning）** | **每用户一个** PERSONAL 租户 | IAM 的 **JIT**（运行时按需） | **无配置**（JIT 自动建/复用） |

- **IdP 只回答「你是谁」**（返回 email/sub）；**租户归属由 IAM 的 `JitProvisioner` 决定**：首次登录该 email → 新建 `gateway_tenant`（`tenant_type='PERSONAL'`）+ Owner 成员；再次登录 → 复用已有个人租户。
- 因此**一个平台级 IdP 可承载无数个个人租户**，不需要为每个用户做任何配置。
- **原理**：IAM `docs/03-E2E2-企业SSO与组织接入.md` §6.1（个人租户生命周期）、§8（平台级 vs 租户级 IdP）、§4.4（PLATFORM 承载）；架构源文档 §7.1 场景 A（个人注册即建个人租户 + Owner）。
- **实现/验证**：`JitProvisioner.resolveMembership`（`isPlatformConfig() → personalMembership()`，`findActiveByOwnerAndType(userId, PERSONAL)` 复用/新建）；集成测试 `OidcSsoIntegrationTest.consumerLoginCreatesPersonalTenant` 已验证。

> 对企业账号同理是「租户级 IdP → 域名路由进组织租户」，两条路并行不悖（docs/03 §8.1）。

### 3.2 澄清一：PLATFORM 当前是「单配置假设」，Google+微软并存需小扩展

- **现状**：`tenant_id='PLATFORM'` 的解析用的是「取唯一一条 ACTIVE OIDC 配置」（`findActiveOidcByTenant` selectOne）——**同一时刻个人登录只支持一个平台 IdP**（要么 Google、要么微软，不能同时从 PLATFORM 出两个入口）；插两行会撞 selectOne 抛错。
- **要「个人登录页同时列 Google + 微软」**需三处小扩展：
  1. PLATFORM 允许多条 ACTIVE OIDC 配置（改查 LIST）；
  2. `authorize` 支持按提供商选择：`authorize?tenant_id=PLATFORM&provider_key=google|microsoft`（或 `idp_config_id=...`）；
  3. 前端登录 hub 从配置动态列个人入口（docs/05 已按此规划）。
- 「共享平台级 IdP」指所有个人用户共用同一种接入，**不意味着只能有一个提供商**。

### 3.3 澄清二：本地账号登录「BFF 转发、验密在 IAM」

- parlant **没有**全权自理本地账号：`POST /api/auth/login`（`routers/auth.py`）只把 `{username,password}` **转发**给 IAM `POST /api/v1/auth/token`（`iam_token_url`）；
- **验密（BCrypt）、查 `gateway_user`/身份、签发 JWT 全在 IAM**；parlant 只把 access_token 回前端，之后请求带 Bearer。
- 合理性：parlant **不建自己的本地账号库、不碰密码、不签发令牌**（seed 账号都在 IAM）；禁用/找回/审计/后续切 SSO 都在 IAM 一处——符合「IAM=身份真相源，业务只消费上下文」。
- 「极简登录页」指 **UI 入口**在 parlant web，**认证逻辑**仍在 IAM。

## 4. parlant-agent 改动清单（文件级）

### 4.1 后端 `.env`（parlant-agent-server/.env）
```dotenv
AUTH_MODE=gateway
JWT_JWKS_URL=http://127.0.0.1:8090/.well-known/jwks.json
IAM_TOKEN_URL=http://127.0.0.1:8090/api/v1/auth/token
JWT_ISSUER=https://www.identityfabric.com   # 可选：与 IAM 签发 iss 一致后开启 iss 校验
JWT_AUDIENCE=parlant-agent-server        # 默认已一致
IAM_SSO_BASE=http://127.0.0.1:8090       # 新增：SSO 跳转的 IAM 基址
```

### 4.2 `app/config/settings.py`（+1 项）
```python
iam_sso_base: str = "http://127.0.0.1:8090"   # SSO authorize 的 IAM 基址（web 经本服务跳转，不直写 IAM URL）
```

### 4.3 `app/routers/auth.py`（+2 端点：`sso/authorize` 供前端跳转 + `me` 供验证/展示；`sso/authorize` 已在 `/api/auth` 白名单）
```python
@router.get("/sso/authorize")
async def sso_authorize(tenant_id: str = "tenant-org-a"):
    """302 到 IAM OIDC authorize（企业=tenant-org-a / 个人=PLATFORM）；浏览器顶层导航，不触发 CORS。"""
    url = f"{settings.iam_sso_base}/api/v1/auth/oidc/authorize?tenant_id={tenant_id}"
    return RedirectResponse(url, status_code=302)
```

> ⚠️ `me` 端点**不能**放 `/api/auth` 前缀：中间件 `PUBLIC_PREFIXES=("/api/auth",)` 是免认证白名单，
> 放那会无鉴权裸奔。应注册为受保护的 `GET /api/me`（中间件自动产 auth_context）：
```python
# routers/auth.py：另挂一个受保护路由（不入 /api/auth 前缀）
# from app.authz import AuthorizationContext, get_context
me_router = APIRouter(prefix="/api", tags=["auth"])

@me_router.get("/me")
async def me(ctx: AuthorizationContext = Depends(get_context)):
    """当前登录用户信息（claims 翻译后返回；「个人账号」验证 tenantId=PERSONAL / roles 用）。
    get_context 只做 401 门槛，任意已认证用户可看自己——不按权限点卡。"""
    return {"user_id": ctx.user_id, "tenant_id": ctx.tenant_id,
            "membership_id": ctx.membership_id,
            "roles": sorted(ctx.roles), "permissions": sorted(ctx.permissions)}
```
（main.py `include_router(me_router)`；轻量替代：前端直接 `decodeJwtPayload` 看 claims，无需后端端点。）

### 4.4 前端 `Login.tsx`（主要改动：三入口 + 回跳收 token）
1. 挂载时读取 IAM 回跳的 `?access_token=`（**收完立即清理 URL + 进工作台**）：
   ```tsx
   useEffect(() => {
     const t = new URLSearchParams(location.search).get('access_token')
     if (t) {
       setAuth(t, userFromToken(t))          // setAuth/userFromToken 已在 store/auth.ts
       history.replaceState(null, '', location.pathname)  // 清掉地址栏/历史的 token
       navigate('/', { replace: true })      // 进工作台（与本地登录/粘贴路径一致）
     }
   }, [])
   ```
   > 理由：`?access_token=` 留在地址栏 = 进浏览器历史 + 可能随 `Referer`/访问日志外泄；`replaceState`
   > 只改地址不刷新、不留历史。登录页额外设 `<meta name="referrer" content="no-referrer">`
   > （或对站外资源 `referrerpolicy="no-referrer"`），双保险防 token 随 Referer 外泄。
2. 新增两个 SSO 按钮（+ 保留本地表单/粘贴令牌）：
   ```tsx
   <button onClick={() => { window.location.href = '/api/auth/sso/authorize?tenant_id=tenant-org-a' }}>企业 SSO 登录</button>
   <button onClick={() => { window.location.href = '/api/auth/sso/authorize?tenant_id=PLATFORM' }}>个人账号登录（Google/微软）</button>
   ```

> `client.ts` / `store/auth.ts` 无需改（已自动带 Bearer + 401 跳登录）。

## 5. IAM 侧配合点（基本就绪，个人账号需补配）

| 项 | 状态 |
|---|---|
| `redirect-uri`（IAM→Keycloak 回调） | `http://localhost:8090/api/v1/auth/oidc/callback`，Keycloak client 已白名单 ✅ |
| `frontend-redirect`（token 回传地址） | `http://localhost:5173/login`，与 parlant web 登录页一致 ✅ |
| 企业 IdP 配置 | `kc-org-a`（tenant-org-a）✅ |
| **个人 IdP 配置（PLATFORM）** | ⚠️ **需补**：`gateway_tenant_idp_config` 插入 `tenant_id='PLATFORM'` 的 Google External / 微软 MSA 配置（docs/03 §10 端点表；含 client_id/secret/claim_mapping） |
| issuer | IAM `https://www.identityfabric.com` ↔ parlant `JWT_ISSUER` 对齐（可选开启校验） |

> **PLATFORM 前置 ≠ 一条配置**：还需要 **Google Cloud Console / Microsoft Entra 的 OAuth 应用注册**（client_id/secret、
> 授权回调 URL 白名单指向 IAM `/api/v1/auth/oidc/callback`）——这是外部平台侧工作，不是 SQL；**个人账号入口在
> 外部应用注册 + IAM 配置都就绪前不可用**，前端按钮应默认隐藏。
> **避免裸 404**（两种二选一，当前 IAM 无 /idp 探测端点）：
> ① IAM 侧补一个只读探测 `GET /api/v1/auth/oidc/idp?tenant_id=PLATFORM`（返回 200/404，几行）；
> ② parlant 侧 `.env` 手动开关 `IAM_SSO_SHOW_PERSONAL=0|1`（最简单，PLATFORM 就绪后改 1 再显示按钮）。

## 6. 时序（企业账号示例；个人账号仅 tenant_id 不同）

```
web 点「企业 SSO」
  → GET /api/auth/sso/authorize?tenant_id=tenant-org-a   (parlant, 302)
  → IAM /api/v1/auth/oidc/authorize?tenant_id=tenant-org-a
  → IAM 302 → Keycloak(8099) 登录页 → 登录 alice@org-a.com
  → Keycloak 302 → IAM /api/v1/auth/oidc/callback?code&state
  → IAM 验签 + JIT + group→role → 签发
  → IAM 302 → http://localhost:5173/login?access_token=...
  → Login.tsx 读到 access_token → setAuth → 后续请求带 Bearer
  → parlant GatewayProvider 拉 JWKS 验签 → 授权生效
```

## 7. 验证步骤

1. 重启 IAM（确认用根 `keys/rsa-private.pem`，`curl / .well-known/jwks.json` 200）。
2. parlant：改 `.env` + 加 `sso/authorize` + `Login.tsx`；重启 server、刷新 web。
3. **企业账号**：点「企业 SSO」→ Keycloak 登录 → 回跳 → `GET /api/agents` 200（AgentOperator）；无令牌 401；缺权限 403。**另验 SSO token 的 `aud=parlant-agent-server`**（解码看，IAM 重签发应满足）+ **`permissions` 覆盖 parlant 全部 9 权限点**（agent:read/build/publish/delete、session:read/send、customer:manage、trace:read、settings:read——逐个请求应 200，缺一个会"某页 403"）。
4. **本地账号**：登录页 username/password（IAM seed 账号）→ 200。
5. **个人账号**（IAM 补配 PLATFORM 后）：点「个人账号登录」→ Google/MSA → 回跳 → **parlant `GET /api/me`**（§4.3 新增）的 `tenant_id`=PERSONAL 租户、`roles` 含 Owner/空（或前端直接解码 JWT 看同一 claims）。
6. 回归：粘贴令牌、SSE `?access_token`、篡改 401。
7. **回调失败路径**（与 IAM 确认行为后验证）：取消 Keycloak 登录 / 域名不在 allowed_domains → 浏览器落在 JSON 错误页（非登录页）——确认本期接受或 IAM 改 `?error=` 回跳。

## 8. P3 收敛（演进路径，本次不做）

- 把 hosted 登录页（picker：企业 SSO / 个人 / 本地 / 注册 / 找回）做到 **IAM**（`/login` + 从 `gateway_tenant_idp_config` 自动列 IdP）。
- parlant web 只留「去登录」跳转（`window.location = IAM_BASE/login?return_to=...`）。
- 理由：登录是身份域共享能力，多业务应用复用、与 SSO 回调同域闭环；业务只消费已授权上下文（docs/01 定位）。
- IAM 侧即 `docs/04-E2E3-P3` 的「登录 UI 能力（后端）」+ 前端 hosted hub 增量。

## 9. 风险与注意

- **SSE**：EventSource 无 header，继续走 `?access_token=`（gateway 已支持），个人/企业账号一致。
- **CORS**：SSO 是浏览器顶层导航跳转，不触发 CORS 预检，无需改。
- **iss 校验**：`JWT_ISSUER` 开启后必须与 IAM issuer 逐字符一致；改一侧同步另一侧。
- **个人账号入口依赖 IAM PLATFORM 配置**：未配置时按钮会 404，建议 IAM 补配后再展示该按钮（或先隐藏）。
- **多租户切换**（个人 ↔ 企业）属 P3 `switch-tenant`（IAM docs/04 §3.4），本次登录页不做租户选择。
- **kid 轮换**：IAM 换钥后 parlant PyJWKClient 最长 5 分钟自动回源，无需操作。
- **URL-token 泄漏面**：SSO 回跳 `?access_token=` 会短暂出现在地址栏/浏览器历史，并可能随 `Referer`/访问日志外泄——Login.tsx 收 token 后**立即 `history.replaceState` 清 query** + 登录页 `no-referrer`（§4.4）；生产形态收敛 HttpOnly cookie / 一次性 code（IAM §13.1），P3 落地。
- **SSO 登出**：本期「退出」仅清 parlant 本地 token，**Keycloak/IAM 会话仍在**——再点「企业 SSO」会秒进、无重新认证；单点登出（IAM `oidc/logout`，预留）延后 P3，需在 UI 文案/文档明示避免误解为真正登出。
- **回调失败停在 JSON 页**：IAM callback 成功才 302 回前端；失败（用户取消 / 域名不在 allowed_domains / state 不符）走异常处理器返回 JSON 状态码，**浏览器停在 JSON 错误页而非登录页**（对照 OidcController `handleCallback` 抛错 + GlobalExceptionHandler）——需与 IAM 确认是否失败也 `?error=` 回跳前端，或本期接受该体验（§7 第 7 步验证）。

## 10. 相关文档

- IAM：`/Users/zhaoshan/workspace/unify-iam-server/docs/03-E2E2-企业SSO与组织接入.md`（§8.1 个人租户、§10 IdP 接入、§13.1 前端承载）
- IAM P3：`/Users/zhaoshan/workspace/unify-iam-server/docs/04-E2E3-P3管理面与账号生命周期设计.md`（登录 UI 能力）
- 本仓库 M1：`docs/06-dev-process/09-M1-API加固与输入审核实施方案.md`、`10-网关接入首阶段最小实现-E2E-1范围.md`（原 `03-production/16/17`，2026-10-09 随 docs 重组迁移）
