"""全局鉴权中间件：除白名单（/health、/docs、/api/internal/*）外全量要求认证。

单一入口做"认证 + 产出上下文"，避免逐路由加导致漏保护（doc09 §4.1）。授权（权限点）由
`deps.require` 在目标路由裁决。逻辑：

- 公开路径（/health、/docs、/redoc、/openapi.json）：放行，不产上下文。
- `/api/internal/*`：服务间信任（runtime↔server），由 4.4 的 X-Internal-Token 保护，不在此验用户。
- 其余 `/api/*`：`provider.authenticate`（取 `Authorization: Bearer` / SSE 走 `?access_token`）→
  成功把 `AuthorizationContext` 写入 `scope["state"]["auth_context"]`（端点经 request.state 读取），
  失败按 AuthError 返回 JSON（CORS 头由外层 CORSMiddleware 补）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.authz.errors import AuthError
from app.authz.provider import AuthProvider

# 显式白名单（避免对 /docs、/health 误拦；/api 其余默认保护）
PUBLIC_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}
INTERNAL_PREFIX = "/api/internal"
# 免认证前缀：登录本身是取令牌的入口（此时还没有凭证），必然公开（doc09/AUTH BFF）。
PUBLIC_PREFIXES = ("/api/auth",)


class AuthzMiddleware:
    def __init__(self, app: Any, *, provider: AuthProvider) -> None:
        self.app = app
        self.provider = provider

    @staticmethod
    def _needs_auth(path: str) -> bool:
        if path in PUBLIC_PATHS or path.startswith(INTERNAL_PREFIX):
            return False
        if path.startswith(PUBLIC_PREFIXES):
            return False
        return path.startswith("/api/")

    async def __call__(
        self, scope: dict[str, Any], receive: Callable, send: Callable
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if not self._needs_auth(path):
            await self.app(scope, receive, send)
            return
        try:
            ctx = await self.provider.authenticate(Request(scope))
        except AuthError as exc:
            response = JSONResponse(
                status_code=exc.status_code, content={"detail": exc.detail}
            )
            await response(scope, receive, send)
            return
        # 登录态请求日志：打印 claims 翻译出的用户/租户/角色/权限（含 dev 模式占位身份）。
        # 只打 ctx 字段、**不打原始 token**（避免凭据进日志）。
        print(
            f"[authz] 已认证 {scope.get('method', '?')} {path} "
            f"user={ctx.user_id} tenant={ctx.tenant_id} "
            f"membership={ctx.membership_id or '-'} roles={sorted(ctx.roles)} "
            f"permissions={sorted(ctx.permissions)}"
        )
        # 共享已认证上下文：端点经 request.state 读取（Starlette Request.state 即 scope["state"]）
        scope.setdefault("state", {})["auth_context"] = ctx
        await self.app(scope, receive, send)