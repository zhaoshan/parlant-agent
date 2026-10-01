"""remote 远程服务工具：通用 HTTP 调用内核 + 按 schema 声明生成工具实例。

背景：前端构建页「新建工具」支持 `source: remote`，但之前只落在 schema 字段上，
loader 的 resolve_tool 只认内置工具 → remote 工具无法真正被引擎调用。本模块把
remote 工具变成**可执行的 HTTP 工具**：

- `make_http_tool(tool_def)`：按 schema 的工具声明（method/url/headers/
  input_schema）生成一个绑定配置的 ToolEntry——用 `_tool_decorator_impl` + 合成
  `__signature__`（@p.tool 装饰器按 inspect.signature 读参数，合成签名让每个
  remote 工具对 LLM 暴露自己的业务参数）。
- 函数体 = 通用 HTTP 内核 `_http_call`：发起请求，支持传入动态 header 与
  request_body，并自动注入 `context.customer_id`。

URL/body 映射规则（远程工具声明即按此写）：
1. url 模板可含 `{param}` 占位：调用时用同名的业务参数填充（如
   `http://127.0.0.1:8300/customer/{customer_id}`）；
2. 未用 `{param}` 占位且不在 body 里的 `customer_id`：自动从 context 注入
   （引擎的会话维度客户，随客户身份切换，见 docs/03-production/09）；
3. GET：剩余业务参数拼成 query string；POST：剩余业务参数进 JSON body；
4. 固定 header 来自声明 `headers`，动态 header 经 `headers` 参数（JSON 字符串）
   传入并合并（LLM 可按需覆盖）；
5. `request_body` 参数（JSON 字符串）存在时整体覆盖 body（精细化控制）。

⚠️ 安全/沙箱问题（SSRF、任意 URL 等）当前不处理，列为待办（需求文档备注）。
"""

from __future__ import annotations

import inspect
import json
from typing import Any, Callable

import httpx
import structlog

import parlant.sdk as p
from parlant.core.services.tools.plugins import _tool_decorator_impl  # noqa: SLF001

logger = structlog.get_logger()

# 工具注册表：schema 声明的 remote 工具名 -> 生成的 ToolEntry
# loader 装配时按 agent 定义逐个生成；同名工具可被多个 agent 复用（id 相同视为同一定义）
_REMOTE_TOOLS: dict[str, Any] = {}


def register_remote_tools(tools: list[Any]) -> list[str]:
    """按 AgentDefinition 的 tools 声明生成/注册 remote 工具，返回新注册的工具名。

    tools: definition.tools.tools（ToolDef 列表）。仅处理 source == "remote"。
    幂等：同名工具已注册则跳过（复用），避免重复加载重复创建。
    """
    registered: list[str] = []
    for t in tools:
        if (t.source or "builtin") != "remote":
            continue
        if t.id in _REMOTE_TOOLS:
            continue
        entry = make_http_tool(t)
        _REMOTE_TOOLS[t.id] = entry
        registered.append(t.id)
    return registered


def resolve_remote_tool(name: str) -> Any:
    """按定义层工具名取已生成的 remote ToolEntry；未知抛 KeyError。"""
    if name not in _REMOTE_TOOLS:
        raise KeyError(f"未知 remote 工具 '{name}'，可用：{sorted(_REMOTE_TOOLS)}")
    return _REMOTE_TOOLS[name]


def make_http_tool(tool_def: Any) -> Any:
    """把一个 remote 工具声明生成绑定了配置的 ToolEntry。

    tool_def: app.models.definition.ToolDef（id/name/description/method/url/
    headers/input_schema/timeout_seconds/consequential）。
    函数体闭包捕获 method/url/headers/timeout；业务参数签名由 input_schema
    的 properties 合成（额外注入可选 headers/request_body 两个控制参数）。
    """
    name = tool_def.name or tool_def.id
    method = (tool_def.method or "GET").upper()
    url_template = tool_def.url or ""
    static_headers: dict[str, str] = dict(tool_def.headers or {})
    timeout = float(tool_def.timeout_seconds or 30.0)
    consequential = bool(tool_def.consequential) if tool_def.consequential is not None else True
    description = tool_def.description or f"调用远程服务 {name}（{method} {url_template}）"

    props: dict[str, Any] = (tool_def.input_schema or {}).get("properties") or {}
    # 必填参数取 input_schema.required（此前被丢弃 → 引擎 tool.required 为空 →
    # 缺参也照发 HTTP → 远程服务 422）。合成签名时必填参数**不带默认值**
    # （parlant：无默认值 = required，plugins.py _find_required_params）；引擎对
    # required 缺参会 CANNOT_RUN 并回传 missing_data，模型须先问客户再调用。
    # 控制参数 headers/request_body 恒为可选。
    required: set[str] = set((tool_def.input_schema or {}).get("required") or [])

    async def _http_call(context: p.ToolContext, **kwargs: Any) -> p.ToolResult:
        return await _http_invoke(
            name=name,
            method=method,
            url_template=url_template,
            static_headers=static_headers,
            timeout=timeout,
            context=context,
            kwargs=kwargs,
        )

    # 合成签名：必填业务参数（无默认值）+ 可选业务参数 + 控制参数 headers/request_body（可选）
    sig_params: list[inspect.Parameter] = [
        inspect.Parameter("context", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=p.ToolContext)
    ]
    for pname in props:
        if pname in required:
            sig_params.append(
                inspect.Parameter(pname, inspect.Parameter.KEYWORD_ONLY, annotation=str)
            )
        else:
            sig_params.append(
                inspect.Parameter(pname, inspect.Parameter.KEYWORD_ONLY, default=None, annotation=str)
            )
    for ctrl in ("headers", "request_body"):
        sig_params.append(
            inspect.Parameter(ctrl, inspect.Parameter.KEYWORD_ONLY, default=None, annotation=str)
        )
    _http_call.__signature__ = inspect.Signature(sig_params, return_annotation=p.ToolResult)
    _http_call.__annotations__["return"] = p.ToolResult

    entry = _tool_decorator_impl(
        name=name,
        description=description,
        consequential=consequential,
    )(_http_call)
    return entry


async def _http_invoke(
    *,
    name: str,
    method: str,
    url_template: str,
    static_headers: dict[str, str],
    timeout: float,
    context: p.ToolContext,
    kwargs: dict[str, Any],
) -> p.ToolResult:
    """通用 HTTP 执行内核（见模块 docstring 的 URL/body 映射规则）。"""
    args = dict(kwargs)
    headers = dict(static_headers)

    # 动态 header（JSON 字符串，LLM 可按需传）
    if args.get("headers"):
        try:
            dyn = json.loads(args.pop("headers"))
            if isinstance(dyn, dict):
                headers.update({str(k): str(v) for k, v in dyn.items()})
        except ValueError:
            logger.warning(f"[remote-tool:{name}] headers 非 JSON，忽略: {args['headers']!r}")

    # request_body（JSON 字符串）整体覆盖 body
    request_body = args.pop("request_body", None)

    # 客户维度自动注入（未显式给 customer_id 时）
    if "customer_id" not in args and context.customer_id:
        args["customer_id"] = context.customer_id

    # URL：{param} 占位替换（用同名业务参数）
    url = url_template
    consumed: set[str] = set()
    for pname, pval in args.items():
        token = "{" + pname + "}"
        if token in url:
            url = url.replace(token, str(pval))
            consumed.add(pname)

    # 剩余参数：GET -> query；POST -> body（request_body 优先覆盖）
    remaining = {k: v for k, v in args.items() if k not in consumed}
    params: dict[str, Any] = {}
    body: Any = None
    if method in ("GET", "DELETE", "HEAD"):
        params = remaining
    elif method in ("POST", "PUT", "PATCH"):
        if request_body:
            try:
                body = json.loads(request_body)
            except ValueError:
                body = {"_raw": request_body}
        elif remaining:
            body = remaining

    try:
        # trust_env=False：本机系统代理（macOS :7899）会劫持 127.0.0.1 请求导致
        # 502（见 CLAUDE.md 五.4）；remote 服务为内网/本地，强制直连。
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            resp = await client.request(
                method=method,
                url=url,
                params=params if params else None,
                json=body,
                headers=headers or None,
            )
    except httpx.HTTPError as exc:
        logger.warning(f"[remote-tool:{name}] HTTP 请求失败: {type(exc).__name__}: {exc}")
        return p.ToolResult(data={"error": f"{type(exc).__name__}: {exc}"})

    try:
        data = resp.json() if resp.content else None
    except ValueError:
        data = {"status": resp.status_code, "text": resp.text[:2000]}

    if resp.status_code >= 400:
        logger.warning(f"[remote-tool:{name}] HTTP {resp.status_code}: {url} -> {data}")
        return p.ToolResult(
            data={
                "error": f"HTTP {resp.status_code}",
                "detail": data,
                "url": url,
                "method": method,
            }
        )
    return p.ToolResult(data={"status": resp.status_code, "data": data})
