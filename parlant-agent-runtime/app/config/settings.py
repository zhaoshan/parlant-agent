"""集中配置：全部从环境变量读取（.env 见 .env.example）。

DB/向量库连接串（MONGO_URI / QDRANT_URL）不硬编码在代码里，必须从 .env
提供（含凭据，不应入库）。缺键时 pydantic 启动即报错，便于发现配置缺失。

Langfuse 三件套（public/secret key + base_url）放在工作区根目录 .env，
由 pydantic 读入后，在 app.utils.observability.configure_langfuse_otel 里
派生成 Parlant OpenTelemetryTracer 需要的 OTEL_* 环境变量。

注意：Parlant 各适配器（litellm 等）用 os.getenv 直接读环境变量，
而 pydantic-settings 只把 .env 读进 Settings 对象、不写回 os.environ。
因此 get_settings() 里先用 load_dotenv 把 .env 装载进 os.environ，
确保 LITELLM_PROVIDER_* / MONGO_URI / QDRANT_URL 等对适配器可见。
"""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

_APP_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _APP_DIR.parent        # parlant-agent-runtime/
_WORKSPACE_DIR = _PROJECT_DIR.parent  # parlant-agent/（根 .env 放 Langfuse 三件套）


def _load_env_files() -> None:
    """把 .env 装载进 os.environ。

    优先级：shell 已导出 > 项目 .env > 根 .env（先载项目、再载根，override=False）。
    """
    for env_path in (_PROJECT_DIR / ".env", _WORKSPACE_DIR / ".env"):
        if env_path.exists():
            load_dotenv(env_path, override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # 工作区根 .env 在前、项目 .env 在后（后者覆盖前者）；缺失文件自动忽略。
        # 注：这与 _load_env_files 的 os.environ 装载相互独立，pydantic 读 env 时
        # os.environ（已由 load_dotenv 填充）优先级最高，两者结果一致。
        env_file=(_WORKSPACE_DIR / ".env", _PROJECT_DIR / ".env"),
        extra="ignore",
    )

    # 基础设施；必需：.env 的 MONGO_URI / QDRANT_URL
    mongo_uri: str
    qdrant_url: str

    # 服务（p.Server 默认端口是 8800）
    host: str = "0.0.0.0"
    port: int = 8000

    # 上游 BFF（parlant-agent-server，阶段3）：定义层由 server 独占写，
    # runtime 启动时经它拉取 published 定义加载（不再直连 Mongo 定义库）。
    server_base_url: str = "http://127.0.0.1:8081"

    # Langfuse（官方后台仅能拿到这三项；OTEL_* 由它们派生）
    langfuse_base_url: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    _load_env_files()  # 先把 .env 装载进 os.environ，再交给 pydantic 解析
    return Settings()
