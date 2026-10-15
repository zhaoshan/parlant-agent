"""配置包：Settings 集中从环境变量读取（.env 见 .env.example）。

DB 连接串（MONGO_URI / MYSQL_URI）不硬编码在代码里，必须从 .env 提供
（含凭据，不应入库）。缺键时 pydantic 启动即报错，便于发现配置缺失。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "parlant-agent-server"
    host: str = "0.0.0.0"
    port: int = 8081  # 8080 常被本机 Docker 占用；plan/README 端口规划同步为 8081

    # 下游：parlant-agent-runtime（Parlant REST，仅内网）
    runtime_base_url: str = "http://127.0.0.1:8000"
    runtime_timeout: float = 30.0

    # 定义层（本服务独占写）；必需：.env 的 MONGO_URI
    mongo_uri: str

    # 用户会话台账 / 未来身份（用户、登录、权限）；必需：.env 的 MYSQL_URI
    mysql_uri: str

    # 跨域（doc09 §4.3 收紧）：默认只放 web 开发来源，逗号分隔多来源，**不再默认 `*`**。
    # dev 下 web 经 Vite 代理 /api→8081（同源），CORS 多数场景不生效；有直连 8081 的其它源
    # （如未来网关形态）在服务端 CORS_ALLOW_ORIGINS 显式加。
    cors_allow_origins: str = "http://localhost:5173"

    # 可观测（langfuse 数据读取）：由本服务代理取数，密钥不下发到浏览器。
    # 未配置时 /api/traces/* 返回 503（说明性错误），不阻断其它功能。
    langfuse_base_url: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    # 鉴权（doc09 §4.1，2026-10-11 收敛为两档）：AUTH_MODE 决定 Provider——
    # dev=开发自动管理员（免令牌全权限，本地不减速，严禁生产）；gateway=接入 IAM（RS256+JWKS，唯一生产形态）。
    # jwt（HS256 本地自签发）已随"登录页收归 IAM hub"淘汰（无入口可发/取 token），见 doc11 §3 形态 B。
    auth_mode: str = "dev"
    jwt_issuer: str = ""                     # 空=不校验 iss；与令牌契约对齐（doc09 §3.4）
    jwt_audience: str = "parlant-agent-server"
    jwt_jwks_url: str = ""                   # AUTH_MODE=gateway（E2E-1）：IAM JWKS 端点
    iam_token_url: str = ""                  # 登录 BFF 的 IAM 令牌端点（POST {username,password}→access_token）；空=本地账号入口 503
    iam_refresh_url: str = ""                # 静默刷新（doc11 附录A）：IAM refresh 端点（POST {refresh_token}→新 access+refresh 轮换）；空=由 iam_token_url 同源推导 /api/v1/auth/refresh
    iam_versions_url: str = ""               # 权限即时吊销（doc11 附录B / user-manual §6 方案①）：IAM 版本点查端点；空=由 iam_token_url 同源推导 /api/v1/auth/versions
    iam_versions_token: str = ""             # X-IAM-Service-Token（对齐 IAM iam.versions.service-token）；空=关闭版本校验（不做即时吊销）
    iam_sso_base: str = ""                   # SSO authorize 的 IAM 后端基址（doc11 §4.1）；gateway 下企业 SSO 经此 302
    iam_hub_base: str = ""                   # IAM 统一登录 hub（unify-iam-web）基址；gateway 模式 web 无 token 时跳它登录，回跳带 ?access_token；dev 不用
    internal_token: str = ""                 # runtime↔server 服务间信任（doc09 §4.4，未配置则不校验）
    token_transport: str = "query"           # SSE 令牌传输（doc09 §4.5）：query=短时 ?access_token（dev，EventSource 兼容）；cookie 预留（生产 HttpOnly）


@lru_cache
def get_settings() -> Settings:
    return Settings()