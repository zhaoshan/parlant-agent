"""AUTH_MODE=jwt：校验本地自签发 JWT（HS256 共享密钥）。

与 `gateway` Provider 是**同一验签器、不同密钥源**：这里用共享密钥对称校验；gateway（E2E-1）
换 RS256 + JWKS（`jwt_jwks_url`）非对称校验，仅"取密钥"一步不同。JWT claims 契约见 doc09 §3.4：
`sub·tenantId·membershipId·roles·permissions·attrs`（iss/aud/exp 按配置校验）。
令牌来源：M1 阶段由 dev/dev-token 等外部签发；全链路签发端点见 doc10 E2E-1。
令牌传输（doc09 §4.5）：常规请求走 `Authorization: Bearer`；SSE（EventSource 带不了 header）
按 `token_transport` 走 `?access_token`（query，默认）或 HttpOnly cookie（生产，预留）。
"""

from __future__ import annotations

from typing import Any

import jwt
from fastapi import Request

from app.authz.context import AuthorizationContext
from app.authz.errors import AuthError
from app.authz.token import claims_to_context, extract_token


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
        token = extract_token(request, self.transport)
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

        return claims_to_context(payload)