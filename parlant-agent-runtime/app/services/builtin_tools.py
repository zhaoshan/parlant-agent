"""定义层声明的内置工具实现（@p.tool，自研——Parlant 框架不提供）。

背景（2026-09-23 核实）：`agent-definition.json` 的 tools[] 里 source="builtin" 的
journey_node_counter / variable_update / tavily_search **在 Parlant 源码中不存在**，
框架只提供 `@p.tool` 装饰器 + ToolEntry/ToolService 机制，工具函数体由我们实现。
loader 按名字 resolve_tool 成 ToolRef 挂到节点/指南上，SDK 收集 ToolEntry 注册进
集成 "built-in" 工具服务，引擎 ToolCaller 在进入 tool 节点/命中指南时调用。

三个工具：
- journey_node_counter：旅程节点访问计数器（按 (agent_id, session_id) 内存计数）。
- variable_update：声明式会话变量写入——把调用方声明的变量值写进 ContextVariableStore
  （key=customer_id 客户级覆盖，优先级最高，见 docs/06-dev-process/02）。
- tavily_search：联网搜索（需 TAVILY_API_KEY；未配置返回提示不抛错）。
"""

import os
from typing import Any

import parlant.sdk as p

# runtime 容器注入（agent_loader.load 时调用），供 variable_update 写变量存储
_container: Any = None


def set_runtime_services(container: Any) -> None:
    """注入 p.Server 的容器（供工具访问 ContextVariableStore/AgentStore）。"""
    global _container
    _container = container


# (agent_id, session_id) -> 当前节点访问次数。单进程开发期够用；多进程需换 Redis 等。
_counters: dict[tuple[str, str], int] = {}


def _log(msg: str) -> None:
    """内置工具调用日志（print 直出 runtime 终端，便于验证）。"""
    print(f"[builtin-tools] {msg}", flush=True)


def _ctx(context: p.ToolContext) -> str:
    """打印 ToolContext 的数据字段（验证是否含 node 等上下文）。"""
    # 只列数据字段；emit_* 是回调不打印
    return (
        f"agent_id={context.agent_id} | session_id={context.session_id} | "
        f"customer_id={context.customer_id} | plugin_data={context.plugin_data!r}"
    )


@p.tool
async def journey_node_counter(
    context: p.ToolContext,
    max_value: int | None = None,
) -> p.ToolResult:
    """Update the current journey-node visit counter.

    每调用一次计数 +1（按会话维度；进入该 tool 节点时引擎调用一次）。
    max_value 用于计算 remaining 与 reached_limit。
    局限：按 (agent_id, session_id) 计数，同一会话内多个计数节点共享（节点维度需
    ToolContext 带节点 id，当前未暴露）；单进程内存，重启清零。
    """
    key = (context.agent_id, context.session_id)
    count = _counters.get(key, 0) + 1
    _counters[key] = count

    _log(
        f"journey_node_counter: [{_ctx(context)}] max_value={max_value} -> count={count}"
    )

    result: dict[str, Any] = {"count": count}
    if max_value is not None:
        result["max_value"] = max_value
        result["remaining"] = max(0, max_value - count)
        result["reached_limit"] = count >= max_value
    return p.ToolResult(data=result)


@p.tool
async def variable_update(
    context: p.ToolContext,
    variable_names: list[str] | None = None,
    variable_selectors: str | None = None,
) -> p.ToolResult:
    """Extract declared session variables and apply their updates.

    真实写入：把声明变量写进 ContextVariableStore（key=customer_id，客户级覆盖，
    引擎按 `customer.id > agent:<id> > 全局` 优先级读取，见 docs/06-dev-process/02）。
    variable_selectors 为 JSON 字符串（@p.tool 仅支持 list 泛型），形如
    `{"varName": {"value": ...}}`；未带 value 或变量未声明则不写（回执状态）。
    依赖 runtime 容器注入（set_runtime_services）。
    """
    if _container is None:
        return p.ToolResult(
            data={"updated": [], "error": "runtime 容器未注入（set_runtime_services 未调用）"}
        )
    try:
        import json as _json

        from parlant.core.agents import AgentStore
        from parlant.core.context_variables import ContextVariableStore

        agent_store = _container[AgentStore]
        cv_store = _container[ContextVariableStore]
        agent = await agent_store.read_agent(p.AgentId(context.agent_id))

        # 解析 agent 声明的变量（name -> variable），与 entity_cq 一致：agent tag + 无标签
        vars_by_name: dict[str, Any] = {}
        for tag in ([p.Tag.for_agent_id(agent.id).id] + [t.id for t in agent.tags] + [""]):
            for var in await cv_store.list_variables(tags=[tag] if tag else []):
                vars_by_name.setdefault(var.name, var)

        selectors: dict[str, Any] = {}
        if variable_selectors:
            try:
                selectors = _json.loads(variable_selectors)
            except ValueError:
                selectors = {"_raw": variable_selectors}

        updated: list[dict[str, Any]] = []
        for name in variable_names or []:
            var = vars_by_name.get(name)
            if not var:
                _log(f"variable_update: [{_ctx(context)}] var={name} -> unknown_variable")
                updated.append({"name": name, "status": "unknown_variable"})
                continue
            sel = selectors.get(name) if isinstance(selectors, dict) else None
            value = sel.get("value") if isinstance(sel, dict) else None
            if value is None:
                _log(f"variable_update: [{_ctx(context)}] var={name} -> no_value（selectors={selectors}）")
                updated.append({"name": name, "status": "no_value"})
                continue
            key = context.customer_id  # 客户级覆盖（最高优先级）
            await cv_store.update_value(var.id, key, value)
            _log(f"variable_update: [{_ctx(context)}] var={name}({var.id}) key={key} -> value={value!r}")
            updated.append({"name": name, "status": "updated", "key": key, "value": value})
        return p.ToolResult(data={"updated": updated})
    except Exception as exc:  # noqa: BLE001 - 工具内吞错并回执，避免打断会话
        return p.ToolResult(data={"updated": [], "error": str(exc)})


@p.tool
async def tavily_search(context: p.ToolContext, query: str) -> p.ToolResult:
    """Search the web using Tavily and return concise result snippets."""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        _log(f"tavily_search: [{_ctx(context)}] query={query!r} -> TAVILY_API_KEY 未配置")
        return p.ToolResult(data={"error": "TAVILY_API_KEY 未配置", "results": []})
    try:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": query, "max_results": 5},
            )
            resp.raise_for_status()
            data = resp.json()
        snippets = [
            {"title": r.get("title"), "url": r.get("url"), "content": r.get("content")}
            for r in data.get("results", [])
        ]
        _log(f"tavily_search: [{_ctx(context)}] query={query!r} -> {len(snippets)} 条结果")
        return p.ToolResult(data={"results": snippets})
    except Exception as exc:  # noqa: BLE001 - 工具内吞错并回执，避免打断会话
        _log(f"tavily_search: [{_ctx(context)}] query={query!r} -> 异常 {type(exc).__name__}: {exc}")
        return p.ToolResult(data={"error": str(exc), "results": []})


# 定义层工具名 -> ToolRef（@p.tool 产物即 ToolEntry，是合法 ToolRef）
BUILTIN_TOOLS: dict[str, Any] = {
    "journey_node_counter": journey_node_counter,
    "variable_update": variable_update,
    "tavily_search": tavily_search,
}


def resolve_tool(name: str) -> Any:
    """按定义层工具名解析 ToolRef；内置未命中则查 remote 远程工具。"""
    if name in BUILTIN_TOOLS:
        return BUILTIN_TOOLS[name]
    # remote 远程服务工具（通用 HTTP 内核，见 http_tools.py）——loader 装配时
    # register_remote_tools 已按 schema 声明生成；此处兜底解析。
    from app.services.http_tools import resolve_remote_tool

    return resolve_remote_tool(name)
