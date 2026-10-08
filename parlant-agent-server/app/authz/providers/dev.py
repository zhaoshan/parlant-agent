"""AUTH_MODE=dev：bootstrap 管理员上下文（含全部权限），本地开发不减速（doc16 §4.1）。

开发仍走统一中间件链路（不让 dev 绕过），只是 Provider 恒定产"已授权管理员上下文"——
因此 require 的权限点全部命中、无 401/403；可选 `X-Dev-User-Id` 头覆盖身份，便于模拟多人。
生产**必须**为 jwt / gateway。
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import Request

from app.authz.context import AuthorizationContext
from app.authz.permissions import ALL_PERMISSIONS


class DevProvider:
    def __init__(self, admin_user_id: str = "dev-admin", tenant_id: str = "workspace") -> None:
        self._admin = AuthorizationContext(
            user_id=admin_user_id,
            tenant_id=tenant_id,
            roles=frozenset({"TenantAdmin"}),
            permissions=ALL_PERMISSIONS,
        )

    async def authenticate(self, request: Request) -> AuthorizationContext:
        uid = request.headers.get("X-Dev-User-Id")
        if not uid:
            return self._admin
        return replace(self._admin, user_id=uid)