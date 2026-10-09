"""AuthProvider 协议 + 按 AUTH_MODE 选实现。

认证（你是谁）与授权（你能做什么）分离：Provider 只负责认证并产出 `AuthorizationContext`；
授权由 `deps.require` 按权限点目录裁决。三种形态（doc09 §8.1）：
- `dev`：bootstrap 管理员上下文（含全部权限），本地开发不减速。
- `jwt`：校验本地自签发 JWT（HS256 共享密钥），独立部署生产默认。
- `gateway`：接入 IAM（RS256+JWKS 验签 + 翻译上下文），E2E-1（doc09 §8.2）。
"""

from __future__ import annotations

from typing import Any, Protocol

from fastapi import Request

from app.authz.context import AuthorizationContext


class AuthProvider(Protocol):
    async def authenticate(self, request: Request) -> AuthorizationContext:
        """从请求解析并校验凭证，产出授权上下文；失败抛 `AuthError`。"""


def get_auth_provider(mode: str, settings: Any) -> AuthProvider:
    """按 AUTH_MODE 组装对应 Provider；未知模式显式报错（防静默降级）。"""
    if mode == "dev":
        from app.authz.providers.dev import DevProvider

        return DevProvider()
    if mode == "jwt":
        from app.authz.providers.jwt import JwtProvider

        return JwtProvider(settings)
    if mode == "gateway":
        from app.authz.providers.gateway import GatewayProvider

        return GatewayProvider(settings)
    raise ValueError(f"未知 AUTH_MODE={mode!r}，可选 dev | jwt | gateway")