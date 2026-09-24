> 来源：docs/concepts/entities/customers.md，Parlant v3.3.1 官方英文文档中文翻译。

# 客户 (Customer)

在 Parlant 中，**客户 (Customer)** 是"任何与智能体互动的人"的代称——无论他们之间真实关系的本质是什么。换句话说，客户可以是一个真实的人、一个机器人，甚至是一个人工客服。

虽然智能体可以匿名运行（不知道自己在和谁交谈），但 Parlant 允许你追踪已注册的客户，并根据他们的身份和偏好提供深度个性化的体验。

通过让你的智能体了解自己在与谁交谈，你可以针对不同的用户细分群体定制交互方式：高价值客户可能会收到高级优惠，新用户可以获得定制的新手引导，等等……

Parlant 让客户注册变得简单，只需要最低限度的身份信息——一个名字就足以开始。

```python
import parlant.sdk as p

async with p.Server() as server:
    # Register a new customer
    customer = await server.create_customer(name="Alice")
```

## 认证
Parlant 旨在作为后端服务存在，把认证 (authentication) 和授权 (authorization) 交给应用层。这意味着，虽然你可以注册客户，但你应该在自己的应用代码中，以任何适合你需求的方式（例如通过 OAuth、JWT 等）处理客户的身份认证。

一旦你识别出了你的客户，就可以把他们的 ID 传递给智能体，让它能够根据已注册的客户来个性化交互。

## 存储
你可以选择客户的存储位置。

默认情况下，Parlant 不会持久化客户，也就是说它们存储在内存中，服务器重启后就会丢失。这便于测试和开发。

如果你希望持久化客户，可以配置 Parlant 使用你选择的数据库。对于本地持久化，我们推荐使用集成的 JSON 文件存储，因为它无需任何设置。对于生产环境，你可以使用内置的 MongoDB，或者其它数据库。

### 持久化到本地存储
这会把客户保存到 `$PARLANT_HOME/customers.json` 下。

```python
import asyncio
import parlant.sdk as p

async def main():
    async with p.Server(customer_store="local") as server:
        # ...

asyncio.run(main())
```

### 持久化到 MongoDB
启动服务器时指定你 MongoDB 数据库的连接字符串即可：

```python
import asyncio
import parlant.sdk as p

async def main():
    async with p.Server(customer_store="mongodb://path.to.your.host:27017") as server:
        # ...

asyncio.run(main())
```

## 客户分组

你还可以把客户划分为不同分组，并通过使用**标签 (tag)** 来控制特定分组的个性化。

例如，你可以为 VIP 客户创建一个标签：

```python
# Create a new tag to represent VIP customers
vip_tag = await server.create_tag(name="VIP")

# Register a new customer
customer = await server.create_customer(name="Alice", tags=[vip_tag.id])
```

> **提示：了解更多**
> 要了解针对特定客户和分组的更高级个性化可能，请查看[变量 (variable)](https://parlant.io/docs/concepts/customization/variables) 一节。

## 添加元数据
你还可以为客户附加自定义元数据 (metadata)，用于存储关于他们的额外信息。这些元数据可用于进一步个性化交互，或为工具调用提供上下文。

```python
customer = await server.create_customer(name="Alice", metadata={
    "external_id": "12345",
    "location": "USA",
})
```

```python
@p.tool
async def get_customer_location(context: p.ToolContext) -> p.ToolResult:
    server = p.ToolContextAccessor(context).server

    if customer := await server.find_customer(id=context.customer_id):
        return p.ToolResult(customer.metadata.get("location", "Unknown location"))

    return p.ToolResult("Customer not found")
```

## 注册客户
虽然你可以使用 SDK 本身来注册客户，但通过你的应用层来处理客户注册往往更实际。这样你能把客户管理与现有的用户认证和授权系统集成起来。

你可以通过使用 Parlant 的 REST API 或原生客户端 SDK 来创建和管理客户。

```python
from parlant.client import ParlantClient

# Change localhost to your server's address
client = ParlantClient("http://localhost:8800")

client.customers.create(
    name="Alice",
    metadata={
        "external_id": "12345",
        "location": "USA",
        "hobby": "reading",
    },
    tags=[TAG_ID]  # Optional: specify tag IDs to assign to the customer
)
```

## 更新客户数据

你可以随时更新客户数据，包括他们的名字、元数据和标签。随着你的应用演进，这有助于让客户信息保持最新。

```python
client.customers.update(
    customer_id=CUSTOMER_ID,
    name="Alice Smith",
    metadata={
        "set": {
            "location": "Canada",
        },
        "remove": ["hobby"],
    },
    tags=[NEW_TAG_ID]  # Optional: specify new tag IDs to assign to the customer
)
```