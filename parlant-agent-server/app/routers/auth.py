"""认证 BFF：`POST /api/auth/login` 把 web 登录凭据转发给 IAM 换 access_token。

定位：令牌**签发权在 IAM**（RS256 私钥持有方），本服务不做校验、只转发——后续请求的验签
由 `GatewayProvider` 完成。走 BFF 而非 web 直连 IAM 的理由：保持 server 是前端唯一入口、
CORS 只放 5173、IAM 留在内网（与 langfuse 代理取数同一姿态，见 traces 路由）。

并发/安全：`iam_token_url` 未配置时返回 503（说明性错误，与 langfuse 未配置口径一致）；
IAM 返回的非 2xx（如用户名密码错）按原状态码转发，不吞错误。
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


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