"""authz：鉴权接缝（doc16 §3.1）。认证（AuthProvider）与授权（permissions + require）分离。

- 认证：`AuthzMiddleware` + `AuthProvider` 按 `AUTH_MODE` 选实现（dev / jwt；未来 gateway E2E-1）。
  中间件全局装配 `AuthorizationContext`（写入 scope["state"]，端点经 request.state 读取）。
- 授权：`require(code)` 路由依赖读到上下文后按权限点目录裁决，缺权限点 → 403。
- 未来接入 IAM（doc17 E2E-1）：只换 `gateway` Provider，路由代码零改动 —— 这是"接缝成立"的证明。

权限点目录（permissions.py）与 unify-iam-server `gateway_permission` 同套 code；
IAM 侧为权威，本文件声明，未来启动校验比对。
"""

from app.authz.context import AuthorizationContext
from app.authz.deps import get_context, require
from app.authz.permissions import (
    AGENT_BUILD,
    AGENT_DELETE,
    AGENT_PUBLISH,
    AGENT_READ,
    ALL_PERMISSIONS,
    CUSTOMER_MANAGE,
    SESSION_READ,
    SESSION_SEND,
    SETTINGS_READ,
    TRACE_READ,
)
from app.authz.provider import AuthProvider, get_auth_provider

__all__ = [
    "AGENT_BUILD",
    "AGENT_DELETE",
    "AGENT_PUBLISH",
    "AGENT_READ",
    "ALL_PERMISSIONS",
    "CUSTOMER_MANAGE",
    "SESSION_READ",
    "SESSION_SEND",
    "SETTINGS_READ",
    "TRACE_READ",
    "AuthProvider",
    "AuthorizationContext",
    "get_auth_provider",
    "get_context",
    "require",
]