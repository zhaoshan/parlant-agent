"""FastAPI 鉴权依赖：get_context（取已认证上下文）+ require(code)（权限点裁决）。

认证已由 `AuthzMiddleware` 全局完成（写入 scope["state"] → request.state）；
本模块只做授权：`require("agent:publish")` 等挂在目标路由函数上，缺权限点 → 403。
未认证（中间件理论上已拦，这里兜底）→ 401。
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.authz.context import AuthorizationContext


def get_context(request: Request) -> AuthorizationContext:
    """取中间件注入的已认证上下文；缺失则按未认证 401（兜底，中间件已全局拦）。"""
    ctx = getattr(request.state, "auth_context", None)
    if ctx is None:
        raise HTTPException(status_code=401, detail="未认证")
    return ctx


def require(*permissions: str):
    """路由授权依赖：`ctx: AuthorizationContext = Depends(require("agent:publish"))`。

    已认证但缺任一权限点 → 403（默认最小权限；未认证 → 401）。
    """
    if not permissions:
        # 仅要求认证、不做细粒度授权（全局默认拒绝的补充场景）
        return get_context

    def _deps(request: Request) -> AuthorizationContext:
        ctx = get_context(request)
        missing = [p for p in permissions if p not in ctx.permissions]
        if missing:
            raise HTTPException(
                status_code=403, detail=f"缺少权限点：{', '.join(missing)}"
            )
        return ctx

    return _deps