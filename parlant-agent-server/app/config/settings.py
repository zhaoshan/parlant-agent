"""配置包：Settings 集中从环境变量读取（.env 见 .env.example）。"""

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

    # 定义层（本服务独占写）
    mongo_uri: str = "mongodb://parlant:parlant-dev@localhost:27017/parlant?authSource=admin"

    # 用户会话台账 / 未来身份（用户、登录、权限）
    mysql_uri: str = "mysql+aiomysql://root:root123456@127.0.0.1:3306/parlant"

    # 跨域：阶段3 前后端分离联调放开（生产收紧为 web 来源）
    cors_allow_origins: str = "*"


@lru_cache
def get_settings() -> Settings:
    return Settings()