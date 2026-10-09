# remote 远程服务工具（平台能力）· 实现说明

> 2026-09-29 落地。背景：构建页「新建工具」一直有 `source: remote` 选项，但只落在
> schema 字段上——loader 的 `resolve_tool` 只认内置工具，remote 工具无法被引擎调用。
> 本改动让 remote 工具成为**可执行的通用 HTTP 工具**。
>
> **通用工具实现/配置总览（内置 + remote + 变量 freshness + 前端 + 踩坑）见
> `docs/06-dev-process/04-工具实现与配置指南.md`**；本文件是智能投顾特性视角的补充说明。

## 一、机制

每个 remote 工具 = **一个绑定自身 HTTP 配置的闭包 ToolEntry**，共享一个通用 HTTP
执行内核：

- 实现：`parlant-agent-runtime/app/services/http_tools.py`
  - `make_http_tool(tool_def)`：按 schema 声明的 `method/url/headers/input_schema`
    生成 ToolEntry。用 `_tool_decorator_impl` + 合成 `__signature__`——`@p.tool`
    装饰器按 `inspect.signature` 读参数（优先读 `__signature__`），合成签名让每个
    remote 工具对 LLM 暴露自己的业务参数（已实测通过签名校验）。
  - `_http_invoke`：通用内核。发出请求、支持动态 header / request_body、自动注入
    `context.customer_id`。
  - `register_remote_tools`：loader `load()` 时按 schema 声明生成并注册（幂等复用）。
- 装配：`agent_loader.load()` → `register_remote_tools(definition.tools.tools)`；
  `resolve_tool(name)` 内置未命中时兜底查 remote（`builtin_tools.resolve_tool`）。
- 引擎调用链路（parlant 原生）：ToolEntry 经 `_enable_tool_refs` 注册进插件服务，
  引擎经 HTTP `/tools/{name}/calls` 调函数体（plugins.py `call_tool`）→ 内核函数。

## 二、URL/body 映射规则（remote 工具声明按此写）

1. **url 模板可含 `{param}` 占位**：调用时用同名业务参数填充。
   ```json
   { "url": "http://127.0.0.1:8300/customer/{customer_id}" }
   ```
2. **customer_id 自动注入**：业务参数未给 `customer_id` 时，从
   `context.customer_id`（会话客户维度）注入 → 客户身份自动切换。
3. **GET**：剩余业务参数拼 query string；**POST/PUT**：进 JSON body。
4. **固定 header** 来自声明 `headers`；**动态 header** 经 `headers` 参数
   （JSON 字符串，LLM 可按需传）合并覆盖。
5. **request_body 参数**（JSON 字符串）存在时整体覆盖 body（精细化控制）。

## 三、schema 形态（新增字段）

```json
{
  "id": "assess_risk",
  "name": "assess_risk",
  "source": "remote",
  "type": "http",
  "method": "POST",
  "url": "http://127.0.0.1:8300/risk/assess",
  "headers": { "Content-Type": "application/json" },
  "timeout_seconds": 10,
  "consequential": true,
  "input_schema": {
    "type": "object",
    "properties": { "risk_level": { "type": "string", "enum": ["C1","C2","C3","C4","C5"] } },
    "required": ["risk_level"]
  }
}
```

`ToolDef` 新增 `method / url / headers` 字段（`app/models/definition.py`）；
前端 `ToolDef` 类型 + 构建页工具编辑器同步（remote 时显示 method/url/headers 配置区）。

## 四、变量 freshness 联动

变量 `tool` 字段绑定 remote 工具 + `freshness_rules`（cron）→ 引擎在变量过期时以
**空参数**自动调工具刷新（`engine.py` 变量加载路径 `arguments={}`）→ 内核自动注入
customer_id 走 URL 占位 → 返回客户数据。智能投顾 5 个变量均绑定
`get_customer_profile` 每小时刷新。

## 五、⚠️ 已知限制（安全/沙箱，列为待办）

- **无 SSRF 防护**：url 来自 schema 声明（非 LLM 直传），但未校验目标主机范围。
- **无鉴权/加密**：远程服务需自行处理。
- **无超时重试分级**：仅单次 httpx timeout。
- **内核函数体 trust_env=False**：内网/本地服务直连，避开本机系统代理劫持
  （macOS :7899 → 502，见 CLAUDE.md 五.4）；外网服务需按需放开。
