> 来源：production/api-hardening.md，Parlant v3.3.1 官方英文文档中文翻译。

# API 增强 (API Hardening)

Parlant 提供了一套健壮的授权与限流系统，用于保护你的 API 免受未授权访问与滥用。本指南将说明如何实现自定义授权策略（authorization policy）与限流器（rate limiter），以加固你的生产环境部署。

## 概述

API 加固系统由两个主要组件组成：

1. **授权策略 (Authorization Policies)** — 控制谁可以访问哪些资源以及执行哪些动作
2. **限流器 (Rate Limiters)** — 通过限制请求频率来防止滥用

这两个组件协同工作，提供全面的 API 保护，并支持基于访问令牌或用户层级设置不同的限制。

## 授权策略

### 理解 AuthorizationPolicy 抽象类

所有授权策略都继承自 `AuthorizationPolicy` 抽象基类，该基类定义了三个关键方法：

```python
class AuthorizationPolicy:
    @abstractmethod
    async def check_permission(
        self,
        request: fastapi.Request,
        permission: AuthorizationPermission
    ) -> bool:
        """Check if the request has permission to perform the action"""
        ...

    @abstractmethod
    async def check_rate_limit(
        self,
        request: fastapi.Request,
        permission: AuthorizationPermission
    ) -> bool:
        """Check if the request is within rate limits"""
        ...

    async def authorize(
        self,
        request: fastapi.Request,
        permission: AuthorizationPermission
    ) -> None:
        """Combined authorization check (permission + rate limit)"""
        # This method usually isn't overriden, as its default implementation
        # calls the two abstract methods in sequence and raises an authorization
        # error if anything is denied.
        ...
```

### 授权权限

Parlant 以枚举（enum）的形式定义了一组全面的权限，覆盖了所有 API 操作：

- Agent 操作（创建、读取、更新、删除）
- 客户 (Customer) 管理
- 会话 (Session) 处理
- 以及更多……

### 内置授权策略

#### DevelopmentAuthorizationPolicy

允许所有动作——仅适用于开发环境：

```python
class DevelopmentAuthorizationPolicy(AuthorizationPolicy):
    async def check_permission(
        self,
        request: fastapi.Request,
        permission: AuthorizationPermission
    ) -> bool:
        return True

    async def check_rate_limit(
        self,
        request: fastapi.Request,
        permission: AuthorizationPermission
    ) -> bool:
        return True
```

#### ProductionAuthorizationPolicy

为生产环境实现更严格的控制，并提供可配置的规则。

## 实现自定义授权策略

当你在真实环境部署中实现自己的授权策略时，通常希望扩展现有的生产策略，而不是从零开始构建。推荐的做法是继承 `ProductionAuthorizationPolicy` 并针对你的具体需求进行定制。

以下是一个参考实现，演示了如何使用 JWT 认证来创建自定义策略：

```python
import parlant.sdk as p

import jwt
from fastapi import HTTPException
from limits import RateLimitItemPerMinute, RateLimitItemPerHour
from limits.storage import RedisStorage
from limits.strategies import SlidingWindowCounterRateLimiter

class CustomAuthorizationPolicy(p.ProductionAuthorizationPolicy):
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        super().__init__()
        self.secret_key = secret_key
        self.algorithm = algorithm

    async def _extract_token(self, request: fastapi.Request) -> dict | None:
        """Extract and validate JWT token from request"""
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.JWTError:
            # Raise 403 for invalid tokens, None for missing tokens is OK
            raise HTTPException(
                status_code=403,
                detail="Invalid access token"
            )

    async def check_permission(
        self,
        request: fastapi.Request,
        operation: p.Operation
    ) -> bool:
        """Enhanced permission checking with M2M token support"""
        token_payload = await self._extract_token(request)

        # If we have a valid M2M (machine-to-machine) token, allow additional operations
        if token_payload and token_payload.get("type") == "m2m":
            m2m_operations = {
                # Allow M2M tokens to perform administrative operations
                p.Operation.CREATE_AGENT,
                p.Operation.READ_AGENT,
                p.Operation.UPDATE_AGENT,
                p.Operation.DELETE_AGENT,
                p.Operation.CREATE_CUSTOMER,
                p.Operation.READ_CUSTOMER,
                p.Operation.UPDATE_CUSTOMER,
                p.Operation.DELETE_CUSTOMER,
                p.Operation.CREATE_CUSTOMER_SESSION,
                p.Operation.LIST_SESSIONS,
                p.Operation.UPDATE_SESSION,
                p.Operation.DELETE_SESSION,
                # Add other operations your M2M integration needs
            }

            if operation in m2m_operations:
                return True

        # For all other cases, delegate to the parent ProductionAuthorizationPolicy
        return await super().check_permission(request, operation)
```

## 限流定制选项

`ProductionAuthorizationPolicy` 提供了多种方式来定制限流行为：

### 1. 覆盖默认限流器（推荐）

最常见的做法是用你自己的 `BasicRateLimiter` 配置覆盖 `self.default_limiter`。**注意 BasicRateLimiter 的限制是按 IP 地址生效的**——因此当你配置 `RateLimitItemPerMinute(100)` 时，它意味着每个 IP 地址每分钟 100 个请求。

```python
from limits import RateLimitItemPerMinute, RateLimitItemPerHour
from limits.storage import RedisStorage
from limits.strategies import SlidingWindowCounterRateLimiter

# Example with Redis storage and custom limits
class CustomAuthorizationPolicy(p.ProductionAuthorizationPolicy):
    def __init__(self, ...):
        super().__init__()

        # ...

        self.default_limiter = p.BasicRateLimiter(
            rate_limit_item_per_operation={
                # Use the default rate limit for most operations
                **self.default_limiter.rate_limit_item_per_operation,
                # Override specific operations with custom limits
                p.Operation.READ_SESSION: RateLimitItemPerMinute(200),
                p.Operation.LIST_EVENTS: RateLimitItemPerMinute(1000),
            },
            # Use a custom storage backend (e.g., Redis)
            storage=RedisStorage("redis://localhost:6379"),
            # Use a custom window strategy
            limiter_type=SlidingWindowCounterRateLimiter,
        )
```

`BasicRateLimiter` 使用 `limits` 库，并支持：
- **限流条目 (Rate limit items)**：`RateLimitItemPerMinute(n)`、`RateLimitItemPerSecond(n)`、`RateLimitItemPerHour(n)`
- **存储选项 (Storage options)**：`RedisStorage()`、`MemoryStorage()`，以及 `limits` 库中的其他存储
- **限流策略 (Limiter strategies)**：`MovingWindowRateLimiter`、`FixedWindowRateLimiter`、`SlidingWindowCounterRateLimiter`

如需完全掌控，你可以通过继承抽象的 `RateLimiter` 类，从零实现你自己的 `RateLimiter`，并将其赋值给 `self.default_limiter`。

### 2. 针对特定操作的自定义限流函数

使用 `self.specific_limiters` 为特定操作提供自定义的限流函数。这些函数接收请求和操作，并返回一个布尔值，用于表示速率是否在限制范围内。

```python
class CustomAuthorizationPolicy(p.ProductionAuthorizationPolicy):
    def __init__(self, ...):
        super().__init__()

        # ...

        self.specific_limiters[p.Operation.DELETE_AGENT] = self._custom_delete_limiter

    async def _custom_delete_limiter(
        self,
        request: fastapi.Request,
        operation: p.Operation
    ) -> bool:
        # Implement your custom logic here
        ...
```

如果你需要同时对权限检查与限流进行完全掌控，也可以直接继承抽象的 `AuthorizationPolicy`，并从零实现所有方法。这会给你完全的灵活性，但需要更多的实现工作。上面展示的方式建立在 `ProductionAuthorizationPolicy` 的健壮基础之上，因此对大多数使用场景来说是推荐的做法。

## 集成你的自定义授权策略

### 使用 configure_container

将你的自定义授权策略与限流器集成到你的 Parlant Agent：

```python
async def configure_container(
    container: p.Container
) -> p.Container:
    container[p.AuthorizationPolicy] = CustomAuthorizationPolicy(
        secret_key="your-jwt-secret-key",
        algorithm="HS256",
    )

    return container
```
```python
async def main():
    # Create Parlant server with custom authorization
    async with p.Server(
        configure_container=configure_container,
    ) as server:
        # Your agent logic here
        await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
```