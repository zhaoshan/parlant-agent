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

    # 鉴权（doc09 §4.1）：AUTH_MODE 决定 Provider（dev=开发自动管理员 / jwt=本地自签发校验 /
    # gateway=接入 IAM，E2E-1 增量）。默认 dev，开发不减速；生产必须 jwt / gateway。
    auth_mode: str = "dev"
    jwt_secret: str = ""                     # AUTH_MODE=jwt：HS256 共享密钥（.env 提供）
    jwt_issuer: str = ""                     # 空=不校验 iss；与令牌契约对齐（doc09 §3.4）
    jwt_audience: str = "parlant-agent-server"
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = 28800            # 令牌有效期（E2E-1 签端点消费；认证侧校验用的是令牌内 exp）
    jwt_jwks_url: str = ""                   # AUTH_MODE=gateway（E2E-1）：IAM JWKS 端点
    iam_token_url: str = ""                  # 登录 BFF 的 IAM 令牌端点（POST {username,password}→access_token），空=登录页仅开发粘贴令牌
    iam_sso_base: str = ""                   # SSO authorize 的 IAM 基址（doc11 §4.1：web 经本服务 302 跳转，不直写 IAM URL）；空=登录页不显示 SSO 入口
    internal_token: str = ""                 # runtime↔server 服务间信任（doc09 §4.4，未配置则不校验）
    token_transport: str = "query"           # SSE 令牌传输（doc09 §4.5）：query=短时 ?access_token（dev，EventSource 兼容）；cookie 预留（生产 HttpOnly）


@lru_cache
def get_settings() -> Settings:
    return Settings()