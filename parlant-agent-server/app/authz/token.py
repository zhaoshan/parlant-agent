"""JWT 令牌解析共用件：从请求取令牌 + claims → AuthorizationContext。

`dev`（bootstrap 上下文）不经过这里；`gateway` Provider 消费（RS256+JWKS 验签后映射 claims）。
提取令牌的传输约定与 claims 到上下文的映射在此统一（doc09 §3.4 / doc10 §3.1）。
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from app.authz.context import AuthorizationContext
from app.authz.errors import AuthError


def extract_token(request: Request, transport: str) -> str | None:
    """取令牌：优先 `Authorization: Bearer`；SSE（EventSource 带不了 header）看 transport。

    - cookie：读 HttpOnly `access_token`（生产预留，doc09 §4.5）。
    - 默认 query：短时 `?access_token=<jwt>`（JWT 是 ASCII，符合本工程"query 传 ASCII"既有约定）。
    """
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    if transport == "cookie":
        return request.cookies.get("access_token")
    return request.query_params.get("access_token") or None


def claims_to_context(payload: Any) -> AuthorizationContext:
    """把 JWT claims（doc09 §3.4 / doc10 §3.1）映射为授权上下文。

    `sub`（或兼容别名 `userId`）缺失即无用户——由 Provider 的验签层在拿到 payload 后调用，
    抛 `AuthError(401)` 交回中间件。
    """
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