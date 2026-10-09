"""授权上下文：业务应用只消费「已授权上下文」的统一交付物。

字段对齐《Gateway 权限体系架构设计》§8.2 的 AuthorizationContext：
`userId / tenantId / membershipId / roles / permissions / attrs(dataAttributes)`。

业务代码只读它、不读任何硬编码身份（ci doc09 §2.2）；未来网关直接产出同构上下文。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# M1 阶段唯一租户（默认工作区）；未来接入 IAM 后由令牌/网关带入真实 tenantId
DEFAULT_TENANT = "workspace"


@dataclass(frozen=True)
class AuthorizationContext:
    user_id: str
    tenant_id: str = DEFAULT_TENANT
    membership_id: str | None = None
    roles: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()
    attrs: dict[str, list[str]] = field(default_factory=dict)  # dataAttributes（数据策略预留）