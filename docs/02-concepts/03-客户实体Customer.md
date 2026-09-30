> 来源：docs/concepts/entities/customers.md，Parlant v3.3.1 官方英文文档中文翻译。

> **⚠️ 官网更新注记（2026-09-30 核对，以 https://www.parlant.io/docs/concepts/entities/customers 为准）**
> 本译文为本地 parlant 仓库 docs/ 的 v3.3.1 快照，官网已更新；经 parlant 源码溯源，
> 下述差异多数为「v3.3.1 代码已支持、仅文档过时」，已按官网回改正文：
> - 回改项：新增 自定义 ID（Custom IDs，`server.create_customer(id=...)`）/ 分组特定指南（Group-Specific Guidelines，`agent.create_observation` + `create_guideline(dependencies=[...])` 门控）/ 认证与会话中途身份（`client.sessions.update(customer_id=...)` 中途认证）/ 与你现有数据库集成（实现 `p.CustomerStore` 接口）/ MongoDB 需 `pip install "parlant[mongo]"`；访问客户方式回改为 `p.Customer.current`；更新客户数据回改为 `customer.metadata.set(...)/.delete(...)` 与 `customer.update(name=...)`
> - 官网新增、未全文重写项：认证（Authentication）论述，完整见官网对应页
> - 源码未确认项：无（本页所列 API 均已溯源确认）

# 客户 (Customer)

在 Parlant 中，**客户 (Customer)** 是"任何与智能体互动的人"的代称——无论他们之间真实关系的本质是什么。换句话说，客户可以是一个真实的人、一个机器人，甚至是一个人工客服。

虽然智能体可以匿名运行（不知道自己在和谁交谈，"guest" 客户），但 Parlant 允许你追踪已注册的客户，并根据他们的身份、偏好和细分群体提供深度个性化的体验。

通过让你的智能体了解自己在与谁交谈，你可以针对不同的用户细分群体定制交互方式：高价值客户可能会收到高级优惠，新用户可以获得定制的新手引导，等等……

Parlant 让客户注册变得简单，只需要最低限度的身份信息——一个名字就足以开始。

```python
import parlant.sdk as p

async with p.Server() as server:
    # Register a new customer
    customer = await server.create_customer(name="Alice")
```

### 自定义 ID（Custom IDs）

默认情况下，Parlant 会自动生成客户 ID。为了直接映射到你现有的用户标识，请传入一个自定义 ID：

```python
customer = await server.create_customer(
    id="usr_12345",  # Your external system's user ID
    name="Alice",
)
```

当你的[工具](/docs/concepts/customization/tools)需要使用相同的 ID 在外部服务（CRM、计费等）中查找客户数据时，这一点尤其有用。

## 客户分组（Customer Groups）

你还可以把客户划分为不同分组，并通过使用**标签 (tag)** 来控制特定分组的个性化。

例如，你可以为 VIP 客户创建一个标签：

```python
# Create a new tag to represent VIP customers
vip_tag = await server.create_tag(name="VIP")

# Register a new customer
customer = await server.create_customer(name="Alice", tags=[vip_tag.id])
```

### 分组特定指南（Group-Specific Guidelines）

要只对特定分组中的客户激活指南，请用自定义匹配器（matcher）创建一条[观察（observation）](/docs/concepts/customization/guidelines)——它检查客户的标签——然后让你的指南[依赖（depend）](/docs/concepts/customization/relationships)于这条观察：

```python
# 1. 定义一个检查 VIP 标签的自定义代码匹配器
async def is_vip(
    ctx: p.GuidelineMatchingContext,
    guideline: p.Guideline
) -> p.GuidelineMatch:
    matched = vip_tag.id in p.Customer.current.tags

    return p.GuidelineMatch(
        id=guideline.id,
        matched=matched,
        rationale="Customer has VIP tag" if matched else "Customer does not have VIP tag",
    )
```

```python
# 2. 使用该匹配器创建一条观察
vip_observation = await agent.create_observation(matcher=is_vip)
```

```python
# 3. 创建只对 VIP 客户激活的指南
vip_guideline = await agent.create_guideline(
    condition="The customer asks about pricing",
    action="Offer the exclusive VIP discount of 20%",
    dependencies=[vip_observation],
)
```

`matcher` 让你用确定性逻辑绕过默认的 LLM 匹配。`dependencies` 参数确保这条指南只会在观察同样匹配时激活，因此非 VIP 客户永远看不到 VIP 专属行为。

> **提示：了解更多**
> 要了解针对特定客户和分组的更高级个性化可能，请查看[变量 (variable)](https://parlant.io/docs/concepts/customization/variables) 一节。

## 元数据（Metadata）

你还可以为客户附加自定义元数据 (metadata)，用于存储关于他们的额外信息。这些元数据可用于进一步个性化交互、为工具调用或自定义匹配器提供上下文。

```python
customer = await server.create_customer(name="Alice", metadata={
    "external_id": "12345",
    "location": "USA",
})
```

下面是一个从工具中访问这些元数据的示例：

```python
@p.tool
async def get_customer_location(context: p.ToolContext) -> p.ToolResult:
    customer = p.Customer.current
    location = await customer.metadata.get("location", "Unknown")
    return p.ToolResult(location)
```

## 更新客户数据（Updating Customer Data）

你可以通过 `Customer` 对象直接更新客户的元数据：

```python
customer = p.Customer.current

# 设置或更新一个元数据值
await customer.metadata.set("location", "Canada")

# 删除一个元数据值
await customer.metadata.delete("plan")

# 更新客户的名字
await customer.update(name="Alice Smith")
```

## 认证与会话中途身份（Authentication and Mid-Session Identity）

Parlant 旨在作为后端服务存在，把认证 (authentication) 和授权 (authorization) 交给应用层。这意味着，虽然你可以注册客户，但你应该在自己的应用代码中，以任何适合你需求的方式（例如通过 OAuth、JWT 等）处理客户的身份认证。

一旦你识别出了你的客户，就可以把他们的 ID 传递给智能体，让它能够根据已注册的客户来个性化交互。

一种常见模式是以 guest 模式开始会话，在客户中途认证后再将会话关联到某个客户：

```python
from parlant.client import ParlantClient

client = ParlantClient(PARLANT_SERVER_URL)

# User authenticates mid-session
client.sessions.update(
    session_id=SESSION_ID,
    customer_id="authenticated_user_123"
)
# 从现在起，智能体可以提供个性化体验
```

## 注册客户（Registering Customers）
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

## 存储（Storage）

你可以选择客户的存储位置。

默认情况下，Parlant 不会持久化客户，也就是说它们存储在内存中，服务器重启后就会丢失。这便于测试和开发。

如果你希望持久化客户，可以配置 Parlant 使用你选择的数据库。对于本地持久化，我们推荐使用集成的 JSON 文件存储，因为它无需任何设置。对于生产环境，你可以使用内置的 MongoDB，或者其它数据库。

> **与你现有的数据库集成**
>
> 如果你已经在自己的数据库中存有客户数据，可以实现 `p.CustomerStore` 接口，直接从那里加载客户。这样，你现有的数据就无需重复存储了。

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

安装 MongoDB 附加组件：

```bash
pip install "parlant[mongo]"
```
