"""AUTH_MODE=jwt：校验本地自签发 JWT（HS256 共享密钥）。

与 `gateway` Provider 是**同一验签器、不同密钥源**：这里用共享密钥对称校验；gateway（E2E-1）
换 RS256 + JWKS（`jwt_jwks_url`）非对称校验，仅"取密钥"一步不同。JWT claims 契约见 doc16 §3.4：
`sub·tenantId·membershipId·roles·permissions·attrs`（iss/aud/exp 按配置校验）。
令牌来源：M1 阶段由 dev/dev-token 等外部签发；全链路签发端点见 doc17 E2E-1。
令牌传输（doc16 §4.5）：常规请求走 `Authorization: Bearer`；SSE（EventSource 带不了 header）
按 `token_transport` 走 `?access_token`（query，默认）或 HttpOnly cookie（生产，预留）。
"""

from __future__ import annotations

from typing import Any

import jwt
from fastapi import Request

from app.authz.context import AuthorizationContext
from app.authz.errors import AuthError


class JwtProvider:
    def __init__(self, settings: Any) -> None:
        self.secret = settings.jwt_secret
        self.algorithm = settings.jwt_algorithm or "HS256"
        self.issuer = settings.jwt_issuer or None  # None=不校验 iss
        self.audience = settings.jwt_audience or None  # None=不校验 aud
        self.transport = getattr(settings, "token_transport", "query") or "query"
        if not self.secret:
            raise RuntimeError("AUTH_MODE=jwt 需要配置 JWT_SECRET")

    async def authenticate(self, request: Request) -> AuthorizationContext:
        token = _extract_token(request, self.transport)
        if not token:
            raise AuthError(
                401, "缺少令牌：请带 Authorization: Bearer <token>（SSE 可走 ?access_token）"
            )
        kwargs: dict[str, str] = {}
        if self.audience:
            kwargs["audience"] = self.audience
        if self.issuer:
            kwargs["issuer"] = self.issuer
        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
                options={"require": ["exp"]},  # 校验 exp
                **kwargs,
            )
        except jwt.ExpiredSignatureError:
            raise AuthError(401, "令牌已过期") from None
        except jwt.InvalidTokenError as exc:
            raise AuthError(401, f"令牌无效：{exc}") from exc

        user_id = str(payload.get("sub") or payload.get("userId") or "")
        if not user_id:
            raise AuthError(401, "令牌缺少 sub/userId")
        return AuthorizationContext(
            user_id=user_id,
            tenant_id=str(payload.get("tenantId") or "workspace"),
            membership_id=payload.get("membershipId"),
            roles=frozenset(payload.get("roles") or []),
            permissions=frozenset(payload.get("permissions") or []),
            attrs=payload.get("attrs") or {},
        )


def _extract_token(request: Request, transport: str) -> str | None:
    """取令牌：优先 `Authorization: Bearer`；SSE（EventSource 带不了 header）看 transport——"""
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    if transport == "cookie":
        # 生产预留：登录时 Set-Cookie(HttpOnly)，SSE 同源自动携带（doc16 §4.5）
        return request.cookies.get("access_token")
    # 默认 query：短时 ?access_token=<jwt>（JWT 是 ASCII，符合"query 传 ASCII"既有约定）
    return request.query_params.get("access_token") or None