# 登录租户管控：parlant 客户租户校验（待办 · 未实施）

> 状态：**已知，方案评估完成，暂不实施**（2026-10-11）。
> 背景：parlant 经 IAM 统一登录 hub 登录时，hub 登录页「企业组织」下拉按 `app_code` 过滤只是 **UX 层**；
> 真正的「只有 parlant 客户租户的用户能进 parlant」需要在 **parlant-agent-server 侧**校验
> `token.tenantId ∈ iam_tenant_application(app=parlant-agent-server)` 的租户集。
> 关联：unify-iam-server `docs/05 §7.6`（收敛接线）、`docs/07`（P3.5 SSO 配置）、`docs/01 P4`（租户隔离激活）。

---

## 1. 问题（一句话）

从 parlant 跳 IAM hub 登录时，用户能选到的租户**取决于业务方是否传 `app=parlant-agent-server`**；
不传 / 手拼 `authorize?tenant_id=X` 即可绕过，拿到**非 parlant 客户租户**的 token 后 parlant 仍会收（验签+aud 通过），
因为没有校验 tenantId 是否属于启用 parlant 的租户。

## 2. 现状边界（三层，逐层诚实）

| 层面 | 边界 | 能否绕过 |
|---|---|---|
| **IAM 真实边界** | 任何配了 **ACTIVE OIDC IdP** 的租户都能 SSO 登录（`/oidc/authorize?tenant_id=X` 可手拼） | 登录页拦不住 |
| **hub 下拉 `app_code` 过滤** | 只控制登录页「企业组织」下拉**显示哪些**（`GET /auth/sso/tenants?app_code=`） | ✅ 业务不传 app / 改 URL → 不生效 |
| **parlant 业务侧** | 验签通过 + 业务权限码（`agent:read` 等） | ❌ 当前**不校验 tenantId 是否 parlant 客户** |

> 补充：IAM `ssoTenants` 的筛选来源是「配了 ACTIVE OIDC IdP 的租户 ∩（可选）iam_tenant_application」，
> **不是** `gateway_tenant.registration_source='SSO'`（tenant-org-a 是 ADMIN 建的，按 registration_source 会漏掉主租户）。

## 3. 方案（parlant 侧客户租户校验）

parlant-agent-server 收到 token 后校验：**`AuthorizationContext.tenant_id` ∈ 启用 parlant 的租户集**
（= `iam_tenant_application(app_code='parlant-agent-server')` 的 tenant_id），不在 → 401/403。
这是「只有 parlant 客户租户的人能进 parlant」的真实边界，不依赖业务方传参数。

两种落地方式：

| 方式 | 做法 | 取舍 |
|---|---|---|
| **A：parlant 直查 IAM 库** | parlant-server 持 IAM 库只读连接，登录后查 `iam_tenant_application` 校验 | 耦合 IAM DB schema，重 |
| **B：IAM 提供校验/下发接口（推荐）** | IAM 加「校验 tenantId ∈ 某 app 客户租户」接口，或把客户租户集随 `/api/auth/mode`（或新接口）下发，parlant 缓存比对 | 解耦、可缓存；需 IAM 侧加小接口 |

- 与 **docs/01 P4「租户隔离激活」** 属同一范畴（parlant 业务层按 tenantId 管控）；P4 落地时一并做。
- 当前 parlant 只有单租户数据，此校验未造成实际泄露，但**不是不存在**——多租户数据一出现即应补。

## 4. 决策与待办

- [ ] 评估 A/B：倾向 **B**（IAM 提供客户租户集/校验接口，parlant 缓存）。
- [ ] IAM 侧：可复用 `TenantApplicationRepository.findTenantIdsByAppCode`（已存在），加公开端点或并入 `/api/auth/mode`。
- [ ] parlant 侧：gateway 验签后追加 tenantId 客户校验；加集成测试（非客户租户 token → 401/403）。
- [ ] 与 hub 下拉 `app_code` 过滤配合：前者是 UX，本校验才是管控，二者都做。

---

## 相关文档

- unify-iam-server `docs/05-IAM前端管理台与统一登录设计.md` §7.6（收敛接线、app_code 过滤）
- unify-iam-server `docs/07-管理面SSO配置-IdP配置与组角色映射.md`（P3.5，SSO 配置管理）
- unify-iam-server `docs/01-总体设计与功能模块拆分.md` §8（P4 租户隔离激活）
