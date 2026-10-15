"""AUTH_MODE=gateway：接入 IAM，RS256 + JWKS 验签（E2E-1）。

与 `jwt` Provider 是**同一验签器、不同密钥源**（doc09 §8.1 / §8.2）：这里换非对称 RS256，
且**签密钥持有方是 IAM**——私钥在 IAM 侧，本服务只有公钥（经 JWKS 下发）可验、无法伪造；
`kid` 换轮由 `PyJWKClient` 按 kid 缓存多把、超出 `lifespan` 自动回源重拉。

claims 契约与本服务一致（doc09 §3.4 / doc10 §3.1）：`sub·tenantId·membershipId·roles·
permissions·attrs`；`iss/aud/exp` 按配置校验（iss/aud 配置为空则不校验对应字段）。

凭据来源与传输，与 jwt 完全一致：常规 `Authorization: Bearer` / SSE `?access_token`（doc09 §4.5）。

注：F401 的 `Request` 仅作类型注解；验签走 `asyncio.to_thread`（PyJWT 需联网拉 JWKS 属阻塞 I/O，
避免卡事件循环）。
"""

from __future__ import annotations

import asyncio
from typing import Any

import jwt
from fastapi import Request

from app.authz.context import AuthorizationContext
from app.authz.errors import AuthError
from app.authz.token import claims_to_context, extract_token
from app.authz.versions import TokenVersionGuard


class GatewayProvider:
    """从 IAM 的 `/.well-known/jwks.json` 取公钥、RS256 验签的 Provider。"""

    def __init__(self, settings: Any) -> None:
        self.jwks_url = settings.jwt_jwks_url or ""
        self.audience = settings.jwt_audience or None  # None=不校验 aud
        self.issuer = settings.jwt_issuer or None  # None=不校验 iss
        self.transport = getattr(settings, "token_transport", "query") or "query"
        # 权限即时吊销（doc11 附录B / user-manual §6 方案①）：每请求点查 IAM 版本，落后/tombstone → 401。
        # iam_versions_token 空 → 关闭（不做即时吊销，靠静默刷新/缩短 TTL 兜底）。
        if not self.jwks_url:
            raise RuntimeError(
                "AUTH_MODE=gateway 需要配置 JWT_JWKS_URL（IAM 的 /.well-known/jwks.json 端点）"
            )
        self._ver_guard = TokenVersionGuard(
            versions_url=settings.iam_versions_url
            or (
                settings.iam_token_url.rstrip("/").rsplit("/token", 1)[0] + "/versions"
                if settings.iam_token_url
                else ""
            ),
            service_token=settings.iam_versions_token,
            app_code=settings.jwt_audience or "parlant-agent-server",
        )
        self._client: jwt.PyJWKClient | None = None  # 懒初始化：首次验签才联网拉，启动不阻塞

    def _jwks(self) -> jwt.PyJWKClient:
        if self._client is None:
            self._client = jwt.PyJWKClient(
                self.jwks_url,
                cache_keys=True,
                lifespan=300,  # kid 缓存留存秒；未知 kid 会回源重拉，换轮天然兼容
            )
        return self._client

    async def authenticate(self, request: Request) -> AuthorizationContext:
        # PyJWKClient 首次/回源是网络 I/O、底层 pyjwt 验签为纯 CPU——整体包到线程池，
        # 避免阻塞单进程事件循环（FastAPI 异步端点共享同一 loop）。
        return await asyncio.to_thread(self._verify, request)

    def _verify(self, request: Request) -> AuthorizationContext:
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
            # 按 token header 的 kid 选公钥；未知/过期 kid 自动回源重拉 JWKS。
            signing_key = self._jwks().get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={"require": ["exp"]},  # 校验 exp
                **kwargs,
            )
        except jwt.ExpiredSignatureError:
            raise AuthError(401, "令牌已过期") from None
        except jwt.InvalidTokenError as exc:
            raise AuthError(401, f"令牌无效：{exc}") from exc
        ctx = claims_to_context(payload)
        # 方案 c（方案① 每请求点查）：token.ver 落后 / tombstone(-1) → 401（配合 b 静默刷新无感续期）；
        # IAM 点查不可用 → 502 fail-closed（可用性耦合，方案① 的显式代价）。路由零改动。
        membership_id = ctx.membership_id
        if membership_id and self._ver_guard.enabled:
            try:
                self._ver_guard.check(membership_id, int(payload.get("ver") or 0))
            except PermissionError as exc:
                raise AuthError(401, str(exc)) from None
            except (ConnectionError, RuntimeError) as exc:
                raise AuthError(502, str(exc)) from None
        return ctx