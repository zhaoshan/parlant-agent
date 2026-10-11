"""认证 BFF：`POST /api/auth/login` 本地账号转发 IAM + `GET /sso/authorize` 企业/个人 SSO 跳转 + `GET /me`。

定位：令牌**签发权在 IAM**（RS256 私钥持有方），本服务不做校验、只转发/跳转——后续请求的验签
由 `GatewayProvider` 完成。走 BFF 而非 web 直连 IAM 的理由：保持 server 是前端唯一入口、
CORS 只放 5173、IAM 留在内网（与 langfuse 代理取数同一姿态，见 traces 路由）。

三种登录（doc11 §1/§3）：
- 本地账号：`POST /login`——转发 IAM `POST /api/v1/auth/token`（验密在 IAM，本服务不碰密码/user 库）。
- 企业/个人 SSO：`GET /sso/authorize`——302 到 IAM OIDC authorize（浏览器顶层导航，不触发 CORS）；
  IAM 验 IdP 后 302 回前端 `?access_token=`（query 传输，见 /me 说明）。
- `GET /me`：受保护的当前用户信息（供 SSO 登录后验证 tenantId/roles；不入 /api/auth 白名单），
  `Depends(get_context)` 只做 401 门槛，任意已认证用户可看自己，不按权限点卡（doc11 §4.3）。

并发/安全：`iam_token_url`/`iam_sso_base` 未配置时对应入口 503/不展示（说明性错误）；IAM 非 2xx 原样转发。
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.authz import AuthorizationContext, get_context
from app.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])
# 受保护路由（不入 /api/auth 白名单）：中间件对 /api/auth/* 免认证，若把 /me 放里面会无鉴权裸奔（doc11 §4.3）。
me_router = APIRouter(prefix="/api", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str | None = "bearer"
    expires_in: int | None = None
    user: dict[str, Any] | None = None


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginBody) -> LoginResponse:
    """把登录凭据转发 IAM `POST {iam_token_url}`，回传 access_token。"""
    settings = get_settings()
    if not settings.iam_token_url:
        raise HTTPException(
            503,
            "IAM 未配置（server .env 缺 IAM_TOKEN_URL）：无法登录；"
            "开发/联调可改用登录页的「粘贴已有令牌」入口。",
        )
    # trust_env=False：本机 macOS 系统代理会劫持 127.0.0.1 请求回 502（既有坑，CLAUDE.md §5.4）
    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        try:
            resp = await client.post(
                settings.iam_token_url,
                json={"username": body.username, "password": body.password},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"IAM 不可达：{type(exc).__name__}: {exc}") from None
    if resp.status_code != 200:
        # 原样转发 IAM 的报错（错误码/文案对用户有意义，如 401 用户名或密码错误）
        detail: str | None = None
        try:
            err = resp.json()
            detail = err.get("detail") or err.get("message") or err.get("error")
        except ValueError:
            pass
        raise HTTPException(resp.status_code, detail or f"IAM 返回 {resp.status_code}")

    data = resp.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        raise HTTPException(502, "IAM 返回成功但缺 access_token")
    return LoginResponse(
        access_token=token,
        token_type=data.get("token_type") or "bearer",
        expires_in=data.get("expires_in"),
        user=data.get("user") or None,
    )


@router.get("/sso/authorize")
async def sso_authorize(tenant_id: str = "tenant-org-a") -> RedirectResponse:
    """302 到 IAM OIDC authorize（企业=tenant-org-a / 个人=PLATFORM）。

    浏览器顶层导航到 IAM（不触发 CORS）；IAM 验 IdP → 302 回前端 `/login?access_token=`。
    `iam_sso_base` 未配置时返回 503（前端据此不展示 SSO 入口，避免裸 404）。
    """
    settings = get_settings()
    if not settings.iam_sso_base:
        raise HTTPException(503, "IAM SSO 未配置（server .env 缺 IAM_SSO_BASE）：无法发起 SSO 登录")
    url = f"{settings.iam_sso_base.rstrip('/')}/api/v1/auth/oidc/authorize?tenant_id={quote(tenant_id)}"
    return RedirectResponse(url, status_code=302)


@router.get("/mode")
async def auth_mode() -> dict[str, Any]:
    """公开返回当前认证模式（`/api/auth` 白名单内免认证，web 启动分流用，doc11 形态 B）。

    - `dev`：web **免登录直进**——写入占位会话（`dev_user`，server 不校验），不走登录页。
    - `gateway`：web 无 token 时跳 `hub_base`（IAM 统一登录 hub）登录，hub 回跳带 `?access_token`。
    """
    settings = get_settings()
    return {
        "mode": settings.auth_mode,
        "dev_user": "dev-admin",  # dev 模式 web 注入的占位身份（与 DevProvider 一致）
        "hub_base": settings.iam_hub_base or "",
    }


@me_router.get("/me")
async def me(ctx: AuthorizationContext = Depends(get_context)) -> dict[str, Any]:
    """当前登录用户信息（claims 翻译后返回）。

    SSO 登录后（尤其个人账号）用 `tenant_id` 确认落在 PERSONAL/企业租户、`roles` 装配是否正确；
    `Depends(get_context)` 由中间件产出的已认证上下文提供，只做 401 门槛。
    """
    return {
        "user_id": ctx.user_id,
        "tenant_id": ctx.tenant_id,
        "membership_id": ctx.membership_id,
        "roles": sorted(ctx.roles),
        "permissions": sorted(ctx.permissions),
    }