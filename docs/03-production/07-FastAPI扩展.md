> 来源：https://www.parlant.io/docs/production/extending-api（官网最新文档，本地 v3.3.1 仓库尚未收录），Parlant 官方英文文档中文翻译。

# 扩展 API（Extending the API）

Parlant 通过一个 FastAPI 应用暴露其功能。内置 API 覆盖了大多数用例，但在特定部署场景下，你可能需要添加自定义端点、中间件或其他扩展。

## `configure_api` 钩子

`Server` 类接受一个 `configure_api` 参数：一个接收 FastAPI app 实例的异步函数。这个钩子在 Parlant 内置路由和中间件配置完成后被调用，让你拥有完整的访问权限来扩展应用。

```python
from fastapi import FastAPI

async def configure_api(app: FastAPI) -> None:
    # Add your customizations here
    pass

async with p.Server(configure_api=configure_api) as server:
    await server.serve()
```

## 添加自定义端点

你可以直接向 FastAPI app 添加自定义路由：

```python
from fastapi import FastAPI

async def configure_api(app: FastAPI) -> None:
    @app.get("/custom/health")
    async def custom_health_check() -> dict[str, object]:
        return {"status": "healthy", "custom": True}

    @app.post("/custom/webhook")
    async def handle_webhook(payload: dict[str, object]) -> dict[str, object]:
        # Process incoming webhook
        return {"received": True}
```

适用于：

* 带应用专属逻辑的自定义健康检查
* 用于外部集成的 Webhook 端点
* 内部调试或管理端点
* 用于自定义监控的指标端点

## 添加中间件

你可以添加 HTTP 中间件来拦截和修改请求与响应：

```python
from fastapi import FastAPI, Request, Response
from typing import Callable, Awaitable

async def configure_api(app: FastAPI) -> None:
    @app.middleware("http")
    async def custom_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Pre-processing
        print(f"Request: {request.method} {request.url.path}")

        response = await call_next(request)

        # Post-processing
        response.headers["X-Custom-Header"] = "my-value"
        return response
```

常见的中间件用例：

* 请求日志与计时
* 添加自定义请求头
* 请求校验或转换
* 自定义认证层

## 自定义 CORS

CORS（跨域资源共享）中间件理想情况下应通过 `AuthorizationPolicy` 类来配置。

内置的 `DevelopmentAuthorizationPolicy` 和 `ProductionAuthorizationPolicy` 默认都允许所有来源（origins），但你可以通过重写策略的 `configure_app` 方法来自定义：

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

class CustomAuthorizationPolicy(p.ProductionAuthorizationPolicy):
    async def configure_app(self, app: FastAPI) -> FastAPI:
        # Add restrictive CORS for production
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "https://your-app.com",
                "https://admin.your-app.com",
            ],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )
        return app
```

然后注册你的自定义策略：

```python
async def configure_container(container: p.Container) -> p.Container:
    container[p.AuthorizationPolicy] = CustomAuthorizationPolicy()
    return container

async with p.Server(configure_container=configure_container) as server:
    await server.serve()
```

注意 `configure_app` 方法在 `configure_api` 钩子之前运行，因此你在其中添加的任何中间件都会被优先应用。由于它与 Parlant 的授权系统集成，这是配置 CORS 的推荐方式。

> [!TIP]
> 需要扩展 API 方面的帮助？参见 [Discord 社区](https://discord.gg/duxWqxKk6J)。
