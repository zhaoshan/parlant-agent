"""本地自签名「迷你 IAM」：为 AUTH_MODE=gateway 的联通测试提供 RS256 公私钥 + JWKS + 签令牌。

背景与定位（doc09 §8.2 / §8.3 / doc10 §4）：
- 真实 IAM（unify-iam-server，P2）未就绪前，用它本地验证 parlant-agent 侧 `GatewayProvider`
  （RS256+JWKS 验签）与 web 登录 BFF 的**全链路**，且不依赖任何外部服务。
- 它此刻**只做签名与验签材料**，不是产品 IAM：私钥在本地文件、端点仅限本机、无用户库/登录审计。
  正式接入时把 `JWT_JWKS_URL` 指向 unify-iam-server 的 `/.well-known/jwks.json` 即可复用同一套
  claims 契约（doc10 §3.1），这段 dev 工具即可退役。

运行（先装依赖：server 的 .venv 已含 PyJWT + fastapi + uvicorn）：
    cd parlant-agent-server
    .venv/bin/python test/gateway_dev_jwks.py --port 8450 --jwt-secret "" --ttl 3600
    另开：把 server .env 的 AUTH_MODE=gateway + JWT_JWKS_URL=http://127.0.0.1:8450/.well-known/jwks.json

端点：
    GET  /                -> 说明
    GET  /.well-known/jwks.json         -> JWKS（含 kid）
    POST /api/v1/auth/token             -> 用固定测试账号签 RS256 access_token（body {username,password}）
       （可作 server `POST /api/auth/login` 的 IAM_TOKEN_URL 上游）

证书：私钥首次生成落在 `~/.parlant-dev/rsa/private.pem`（0600）；k8s/Jenkins 或并行跑会共享，正常。
"""

# NOTE：本文件**不能**放 `from __future__ import annotations`——`TokenBody`/`LoginBody` 是
# `make_app` 内的**局部类**，字符串注解 FastAPI 无法解析（会退化为 query 参数 / 422）。
# 让它保持真实类注解即可（dict/JSONResponse 等模块级或内置注解无此问题）。

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

# 路径引导：保证无论从哪个 cwd 运行都能 `import jwt` 用到 server .venv 的 PyJWT
_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

import jwt  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
import uvicorn  # noqa: E402
from pydantic import BaseModel  # noqa: E402

# 固定测试账号（本工具仅作联通验证，非真实用户）
_ACCOUNTS = {"admin": "admin123", "operator": "op123"}

# 与 doc09 §3.4 / doc10 §3.1 权限目录对齐的可签权限（演示用）
_ALL_PERMS = {
    "agent:read", "agent:build", "agent:publish", "agent:delete",
    "session:read", "session:send", "customer:manage", "trace:read", "settings:read",
}


def _load_or_gen_key(key_dir: Path) -> tuple[bytes, dict]:
    """加载或生成 RSA 私钥（PEM）与 JWK；返回 (私钥PEM, jwk)。"""
    key_dir.mkdir(parents=True, exist_ok=True)
    priv = key_dir / "private.pem"
    if priv.exists():
        pem_bytes = priv.read_bytes()
        private_key = serialization.load_pem_private_key(pem_bytes, password=None)
    else:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem_bytes = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
        priv.write_bytes(pem_bytes)
        os.chmod(priv, 0o600)

    public_numbers = private_key.public_key().public_numbers()
    kid = "dev-key-1"
    jwk = {
        "kty": "RSA",
        "kid": kid,
        "n": _b64(int_to_bytes(public_numbers.n)),
        "e": _b64(int_to_bytes(public_numbers.e)),
        "alg": "RS256",
        "use": "sig",
    }
    return pem_bytes, jwk


def int_to_bytes(n: int) -> bytes:
    return n.to_bytes((n.bit_length() + 7) // 8, "big") or b"\x00"


def _b64(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_app(jwks_url: str, ttl: int) -> FastAPI:
    key_dir = Path.home() / ".parlant-dev" / "rsa"
    pem_bytes, jwk = _load_or_gen_key(key_dir)
    private_key = serialization.load_pem_private_key(pem_bytes, password=None)

    jwks_doc = {"keys": [jwk]}

    class TokenBody(BaseModel):
        username: str
        password: str

    app = FastAPI(title="parlant-dev-mini-iam")

    @app.get("/")
    def root() -> dict:
        return {
            "service": "parlant-dev-mini-iam",
            "kids": [jwk["kid"]],
            "jwks": jwks_url,
            "login": "POST /api/v1/auth/token",
        }

    @app.get("/.well-known/jwks.json")
    def jwks() -> JSONResponse:
        return JSONResponse(jwks_doc)

    @app.post("/api/v1/auth/token")
    def token(body: TokenBody) -> dict:
        if body.password != _ACCOUNTS.get(body.username):
            return JSONResponse({"detail": "用户名或密码错误"}, status_code=401)
        now = int(time.time())
        claims = {
            "sub": f"u-{body.username}",
            "tenantId": "workspace",
            "membershipId": f"mem-{body.username}",
            "roles": ["TenantAdmin", "Developer"],
            "permissions": sorted(_ALL_PERMS),
            "iss": "parlant-dev-mini-iam",
            "aud": "parlant-agent-server",
            "exp": now + ttl,
            "iat": now,
            "jti": str(uuid.uuid4()),
        }
        token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": jwk["kid"]})
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": ttl,
            "user": {"user_id": claims["sub"], "user_name": body.username, "roles": claims["roles"]},
        }

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="parlant 本地迷你 IAM：JWKS + 签 RS256 令牌（联通测试用）")
    parser.add_argument("--port", type=int, default=8450)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--ttl", type=int, default=3600, help="签出令牌有效期（秒）")
    args = parser.parse_args()
    jwks_url = f"http://127.0.0.1:{args.port}/.well-known/jwks.json"
    print(f"✅ 迷你 IAM 已启动：{args.host}:{args.port}")
    print(f"   JWKS: {jwks_url}")
    print(f"   IAM 令牌端点（登录 BFF 上游）: http://127.0.0.1:{args.port}/api/v1/auth/token")
    print("   测试账号: admin/admin123（TenantAdmin+全部权限）| operator/op123")
    uvicorn.run(make_app(jwks_url, args.ttl), host=args.host, port=args.port)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已退出")