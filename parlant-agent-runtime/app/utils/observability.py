"""Langfuse 追踪接入（OTLP 方案，无 Langfuse SDK）。

原理：Parlant 的 OpenTelemetryTracer 启动时自设全局 TracerProvider，
并 purely 通过环境变量导出 OTLP（OTEL_EXPORTER_OTLP_TRACES_ENDPOINT / _HEADERS）。
所以这里只需两件事：

1. instrument_fastapi(app)：给 Parlant 的 FastAPI app 挂 instrumentor，
   自定义 /internal/* 端点与 Parlant 自带端点进入同一条 trace 管道；
2. _request_hook：把请求头里的用户/会话/Agent 上下文写成 Langfuse
   OTLP 约定的 trace 级属性（https://langfuse.com/docs/opentelemetry/get-started）：
   - x-user-id    → langfuse.user.id
   - x-session-id → langfuse.session.id
   - x-tags       → langfuse.tags（逗号分隔，字符串数组）
   - x-agent-id   → parlant.agent.id（自定义维度，按 Agent 过滤）

注意：hook 挂在 server span（trace 根）上，属性即对整个 trace 生效。
"""

import base64
import os
from typing import Any

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as HttpOTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import Decision, Sampler, SamplingResult

from app.config import Settings

_LANGFUSE_OTLP_TRACES_PATH = "/api/public/otel/v1/traces"
_LANGFUSE_INGESTION_VERSION_HEADER = "4"


def configure_langfuse_otel(settings: Settings) -> None:
    """由 LANGFUSE_* 三件套派生 Parlant OpenTelemetryTracer 读取的 OTEL_* 环境变量。

    必须在 p.Server 进入（_define_tracer 读 env）之前调用。
    已显式设 OTEL_EXPORTER_OTLP_TRACES_ENDPOINT 时视为手工模式，直接跳过。
    """
    if os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"):
        return  # 手工模式：endpoint/headers 全由使用者控制

    if not (
        settings.langfuse_base_url
        and settings.langfuse_public_key
        and settings.langfuse_secret_key
    ):
        return  # 未配置 Langfuse → Parlant 回退 LocalTracer（不导出）

    base_url = settings.langfuse_base_url.rstrip("/")
    os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = base_url + _LANGFUSE_OTLP_TRACES_PATH
    os.environ.setdefault("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")  # Langfuse 只支持 HTTP
    os.environ.setdefault("OTEL_SERVICE_NAME", "parlant-agent-runtime")
    # Parlant span 携带完整 prompt/上下文，批量较大；默认 10s 超时在本机网络上
    # 频繁 "Failed to export span batch due to timeout"，放宽到 30s（单位：毫秒）
    os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_TIMEOUT", "30000")

    raw = f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}"
    auth = base64.b64encode(raw.encode()).decode()
    # base64 字符集不含逗号 → raw 直接入值安全。OTel parse_env_headers(liberal=True)
    # 对 base64（无 %）做 unquote 是 no-op（v1.37.0 util/re.py 已核实），无需 URL 编码。
    os.environ["OTEL_EXPORTER_OTLP_TRACES_HEADERS"] = (
        f"Authorization=Basic {auth},x-langfuse-ingestion-version={_LANGFUSE_INGESTION_VERSION_HEADER}"
    )


# 请求头（小写）→ Langfuse trace 级属性
_TRACE_ATTRIBUTE_HEADERS: dict[str, str] = {
    "x-user-id": "langfuse.user.id",
    "x-session-id": "langfuse.session.id",
    "x-agent-id": "parlant.agent.id",
}
_TAGS_HEADER = "x-tags"

# 排除规则（逗号分隔正则，命中 URL path 即不建 span）：
# - health          探活（避免监控噪音）
# - /chat           内置聊天 UI 静态页
# - /$              根路径重定向到 /chat
# - /sessions       会话 REST 的 UI 轮询/WebSocket（聊天 UI 与引擎执行无关的 HTTP 壳；
#                   引擎执行是独立 trace，根 span 为 process，不受此排除影响）
# - /logs           Parlant 自带 websocket-logger 后台任务自连 /logs 推日志，
#                   每条日志一个 "HTTP websocket send" span，是最大噪声源
# 保留：/internal/*（阶段2 端点，需 trace 属性挂钩）、/agents /terms 等配置类端点
_EXCLUDED_URLS = "health,/chat,/$,/sessions,/logs"

_instrumented_app_ids: set[int] = set()


class _HttpNoiseSampler(Sampler):
    """按 span 名丢弃 HTTP 噪声。websocket 的 send/receive 每帧一个 span
    （Parlant 自带 websocket-logger 会持续推日志），量最大且无语义，直接 DROP。
    引擎执行 span（process 等）由 Parlant 自己的 TracerProvider 发出，不经过这里。"""

    _NOISE_PREFIXES = ("HTTP websocket",)

    def should_sample(
        self,
        parent_context: Any,
        trace_id: int,
        name: str,
        kind: Any = None,
        attributes: Any = None,
        links: Any = None,
        trace_state: Any = None,
    ) -> SamplingResult:
        if name.startswith(self._NOISE_PREFIXES):
            return SamplingResult(Decision.DROP)
        return SamplingResult(Decision.RECORD_AND_SAMPLE)

    def get_description(self) -> str:
        return "HttpNoiseSampler"


def _build_http_tracer_provider() -> SDKTracerProvider | None:
    """给 FastAPI 仪器单独建一个 Provider（与 Parlant 引擎的 Provider 并列）。

    原因：Parlant 的 OpenTelemetryTracer 自设全局 Provider 且无法事后换 sampler，
    而 websocket 噪声按 URL 排除不掉（逐帧 send span 的来源路径不受 excluded_urls
    约束），所以 HTTP 层用自己的 Provider + 名称 sampler，引擎层保持原样。
    未配置 OTLP endpoint（langfuse 未启用）时返回 None，即不追踪 HTTP 层。
    """
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    if not endpoint:
        return None
    provider = SDKTracerProvider(sampler=_HttpNoiseSampler())
    exporter = HttpOTLPSpanExporter(endpoint=endpoint)  # headers/timeout 自动读 OTEL_* env
    provider.add_span_processor(BatchSpanProcessor(span_exporter=exporter))
    return provider


def _request_hook(span: trace.Span, scope: dict[str, Any]) -> None:
    if span is None or not span.is_recording():
        return
    # ASGI scope 的 headers 是 (bytes, bytes) 元组列表，键值都要 decode
    headers = {
        k.decode().lower(): v.decode()
        for k, v in scope.get("headers", [])
    }

    for header, attribute in _TRACE_ATTRIBUTE_HEADERS.items():
        if value := headers.get(header):
            span.set_attribute(attribute, value)

    if raw := headers.get(_TAGS_HEADER):
        tags = [t.strip() for t in raw.split(",") if t.strip()]
        if tags:
            span.set_attribute("langfuse.tags", tags)


def instrument_fastapi(app: FastAPI) -> None:
    """给 app 挂 FastAPI instrumentor（幂等），HTTP span 走独立 Provider 导出。"""
    if id(app) in _instrumented_app_ids:
        return
    provider = _build_http_tracer_provider()
    FastAPIInstrumentor().instrument_app(
        app,
        server_request_hook=_request_hook,
        excluded_urls=_EXCLUDED_URLS,
        tracer_provider=provider,  # None 时回退全局 Provider（引擎管道）
    )
    _instrumented_app_ids.add(id(app))
