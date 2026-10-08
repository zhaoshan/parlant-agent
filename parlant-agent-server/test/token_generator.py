"""生成用于手动验证 4.1/4.2 鉴权的测试 JWT。

密钥来源 = parlant-agent-server 的 `.env` 里的 JWT_SECRET（与认证 Provider 同一把），
故签出的令牌必然能验签通过（iss/aud/exp 一并按 .env 契约带好）。

用法（任一路径下均可，PyJWT 由 uv 提供）：
    uv run python test/token_generator.py                          # 打印 ADMIN + LIMITED 两枚（默认）
    uv run python test/token_generator.py --sub u-1001 --perms settings:read,trace:read
    uv run python test/token_generator.py --ttl -7200              # 负值=过期令牌（验证 exp 401）

输出到 stdout；shell 里可用 tee 落盘后按前缀拾取：
    uv run python test/token_generator.py | tee /tmp/tokens.txt
    ADMIN=$(grep '^ADMIN=' /tmp/tokens.txt | cut -d= -f2)
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import jwt

# ---- 路径引导：无论从哪个 cwd 运行，都能 import app 并读到 server/.env ----
_SERVER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_SERVER_ROOT)  # get_settings() 的 env_file=".env" 按 cwd 解析 → 必须切回 server 根
sys.path.insert(0, _SERVER_ROOT)  # 让 from app.config ... 能被导入

from app.config import get_settings  # 须在路径引导之后导入（E402 未启用，无需 noqa）

# 演示：全权限管理员（对照 200 / 403 用）
ALL_PERMS = [
    "agent:read",
    "agent:build",
    "agent:publish",
    "agent:delete",
    "session:read",
    "session:send",
    "customer:manage",
    "trace:read",
    "settings:read",
]


def make_token(sub: str, perms: list[str], ttl: int = 3600) -> str:
    s = get_settings()
    return jwt.encode(
        {
            "sub": sub,
            "aud": s.jwt_audience,
            "exp": int(time.time()) + ttl,  # ttl<0 即过期，验证 exp 拦截
            "roles": ["AgentOperator"],
            "permissions": perms,
        },
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="生成测试 JWT（读 server/.env 同款 JWT_SECRET；不指定参数则打印 ADMIN+LIMITED 两枚）"
    )
    parser.add_argument("--sub", default=None, help="sub/userId；可与 --perms 配合签自定义令牌")
    parser.add_argument("--perms", default=None, help="逗号分隔权限点，如 settings:read,trace:read（搭配 --sub）")
    parser.add_argument("--ttl", type=int, default=3600, help="生效秒数；负值=过期令牌（验证 exp→401）")
    args = parser.parse_args()

    if args.sub is not None or args.perms is not None:
        perms = [p.strip() for p in (args.perms or "").split(",") if p.strip()]
        print(f"TOKEN={make_token(args.sub or 'u-1001', perms, args.ttl)}")
        return

    print("ADMIN=" + make_token("u-1001", ALL_PERMS, args.ttl))
    print("LIMITED=" + make_token("u-1002", ["trace:read"], args.ttl))


if __name__ == "__main__":
    main()