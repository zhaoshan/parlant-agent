> 来源：docs/concepts/customization/tools.md，Parlant v3.3.1 官方英文文档中文翻译。

# 工具（Tools）

Parlant 提供了一种受引导的工具使用方式，并与它的指南系统紧密集成。

Parlant 的工具调用方式是从零开始构建的。它很可能比你从大多数 LLM API（包括 [MCP](https://modelcontextprotocol.io/introduction)）中所熟悉的工具调用机制更加全面。这是因为它的构建目的是与其基于指南的行为控制实现深度、无缝的集成。

### 理解工具的使用

在 Parlant 中，工具总是与特定的指南相关联。只有当其关联的指南与对话相匹配时，工具才会执行。这种设计创造了一条清晰的意图链：由指南决定工具何时以及为何被使用，而不是将其交给 LLM 的判断（后者充斥着错误）。

在 Parlant 中，**业务逻辑**（编码在工具中）被有意识地从**呈现**（用户界面）关注点，也就是从由指南控制的面向客户的行为中分离出来。

这样，你可以让开发者用代码完整地编写 API 逻辑并加以完全控制——将这些工具提供给智能体的"工具库"（tool shed）。然后，业务专家可以独立地用自然语言定义指南，决定这些工具何时以及如何被使用，而无需介入底层代码。这种关注点分离是 Parlant 的一项关键设计原则，从而产生更清晰、更易维护的系统。

#### 对话式 UI 与图形化 UI

打个比方，你可以把指南和工具类比为图形化 UI 框架中的控件（Widgets）和事件处理器（Event Handlers）。一个 GUI 按钮有一个 `onClick` 事件，我们可以把它与某个 API 函数关联起来，表示 _"当这个按钮被点击时，运行这个函数。"_。同理，在 Parlant（本质上是一个对话式 UI 框架）中，指南就像按钮，工具就像 API 函数，而关联（就像注册一个事件处理器）将二者连接起来，表示 _"当这条指南被应用时，运行这个工具。"_

下面是一个具体示例来说明这些概念：
> * **条件：** 用户询问服务功能
> * **动作：** 理解他们的意图并查阅文档来回答
> * **工具关联：** `[query_docs(user_query)]`

在这里，只有当指南指示我们应当为这次用户交互查阅文档之后，文档查询工具才会运行。

## 编写工具

要编写一个工具，你需要定义一个函数，其第一个参数为 `ToolContext`，后面跟着你想传递给工具的任何其他参数。该函数应返回一个 `ToolResult`。

以下是 Parlant 智能体中任何工具的基本结构：

```python
import parlant.sdk as p

@p.tool
async def tool_name(context: p.ToolContext, param1: str, param2: int) -> p.ToolResult:
  """Multi-line tool description.
  This is readable by the agent and helps it decide if/when to run this tool.
  """
  ...
```

为了更具体地说明，下面是一个简单示例：一个将产品取入智能体上下文的工具：

```python
import parlant.sdk as p

@p.tool
async def find_products(context: p.ToolContext, query: str) -> p.ToolResult:
    """Fetch products based on a natural-language search query."""

    # Simulate fetching the balance from a database or API
    products = await MY_DB.get_products(query=query)

    return p.ToolResult(balance)
```

#### 可选参数

你还可以使用 `typing` 模块中的 `Optional` 类型为工具定义可选参数。这允许工具在不提供该参数值的情况下被调用。

```python
from typing import Optional
import parlant.sdk as p

@p.tool
async def find_products(
  context: p.ToolContext,
  query: str,
  limit: Optional[int]
) -> p.ToolResult:
    default_limit = 10
    products = await MY_DB.get_products(query=query, limit=limit or default_limit)

    return p.ToolResult(products)
```

## 将工具连接到你的智能体

要让你的智能体运行某个工具，你需要指定在什么条件下它可以被评估和调用。如前所述，这种方法有助于消除误报工具调用，这是 LLM 的常见问题。

```python
@p.tool
async def my_tool(context: p.ToolContext) -> p.ToolResult:
  ...

await agent.create_guideline(
    condition=CONDITION,
    action=ACTION,
    tools=[my_tool],
)
```

如果工具本身就隐含了动作，你可以跳过手动指定它，让 Parlant 从工具的描述中推断出来。如下所示：

```python
await agent.attach_tool(condition=CONDITION, tool=my_tool)
```

## 工具结果（ToolResult）

`ToolResult` 是一个封装了工具调用结果的特殊对象。

它有五个你可以使用的属性。虽然大多数时候你只会用到 `data` 属性，但了解其他属性是值得的，因为它们可以实现一些有趣的用例：`data`、`metadata`、`control`、`canned_responses` 和 `canned_response_fields`。

> **工具结果的存续期（Lifespan）**
>
> 与许多通用智能体框架不同，Parlant 专门并有意识地针对构建对话式智能体进行了优化。因此，其架构针对对话式应用优化了工具调用的默认行为。
>
> 为此，工具结果默认保存在会话中，因此在整段交互会话期间都可供智能体引用。这意味着后续的指南匹配和工具调用会自动获知工具先前的返回结果。这对于需要稍后引用的结果（如账户余额、商品 ID 或其他产品信息）非常有用。
>
> 例如，如果你调用了一个返回产品名称和 ID 的工具，并且——在客户通过选择某个特定产品作出回应之后——你又调用了另一个接受 `product_id` 参数的工具，那么智能体将能够利用前一个工具的结果，自动从上下文中填充该参数。例如：

```python
@p.tool
async def get_products(context: p.ToolContext, query: str) -> p.ToolResult:
    products = await MY_DB.get_products(query=query)
    return p.ToolResult(data=products)

@p.tool
async def get_product_details(context: p.ToolContext, product_id: str) -> p.ToolResult:
    # The agent will be able to parameterize the right `product_id`
    # if the previous tool call was already made in the session.
    product = await MY_DB.get_product(product_id=product_id)
    return p.ToolResult(data=product)
```

### 工具结果的属性

让我们看看这些属性各自是什么、用途是什么，以及如何使用它们：

#### Data（数据）

`data` 属性包含工具的主要输出。它可以是任意可 JSON 序列化的类型，例如字符串、列表或字典。

这是 `ToolResult` 中*始终*必需的唯一属性，因为它是智能体用来理解交互事件历史的唯一属性。也就是说，如果你在 `data` 属性中不返回任何内容，智能体就不会被告知你的结果，也就无法利用它来引导交互。

```python
# Example 1
return p.ToolResult(data="This is the result of my tool call")

# Example 2
return p.ToolResult(data={"appointments": [
  { "id": "123", "date": "2023-10-01 10:00" },
  { "id": "456", "date": "2023-10-02 11:00" },
]})
```

#### Metadata（元数据）

`metadata` 属性是一个可选字典，可用于存储关于该工具调用的额外信息。

智能体完全感知不到这些元数据，但你可以使用 REST API 客户端从响应中获取它们。这使得它适合发回关于响应的额外信息，这些信息可以为你的前端增加价值。

此处一个经典用例是返回 RAG 信息来源（例如 URL、文档 ID 等），可用于在前端展示信息来源。另一个用例是返回生成图表或其他可视化内容的图片链接，这些内容可以在前端显示。

```python
return p.ToolResult(
  data=ANSWER,
  metadata={ "sources": [{"url": s.url, "title": s.title} for s in ANSWER_SOURCES]},
)
```

```python
return p.ToolResult(
  data="The profit margin is 20%",
  metadata={ "generated_chart_url": "https://example.com/chart.png" },
)
```

> **注意存续期**
>
> 由于元数据主要在访问会话事件时才有用，因此通常只有搭配 `lifespan: "session"`（默认值）使用才有意义。如果你使用 `lifespan: "response"`，该元数据将不会出现在会话事件中，因此前端无法访问。

#### Control（控制）

`control` 属性允许你为智能体和引擎指定控制指令。

目前有两种可用的控制指令：
- `"mode": p.SessionMode`：允许你将会话置于手动模式，这意味着智能体将不再自动生成响应。这特别适用于人工接管（human-handoff）场景，此时你希望暂停智能体的自动响应，让人类操作员接管。
- `"lifespan": p.Lifespan`：控制 `ToolResult` 应存续多久。有两个选项：
  - `"session"`：结果将被保存，并在整个会话期间供智能体使用。这是默认值。
  - `"response"`：结果仅在当前响应期间可用。这对于超出当前响应就不再需要的临时结果很有用，例如报告错误，或提供极短暂的信息。

```python
return p.ToolResult(
  data="Transferring to a human agent",
  # Once this tool result is returned, the agent will not generate any more responses
  # until the session is put back on automatic mode using an API call.
  control={ "mode": "manual" },
)
```

```python
return p.ToolResult(
  data="Encountered an error while fetching data",
  # This tool result will not be saved in the session.
  # The agent will only be aware of it during the current response.
  control={ "lifespan": "response" },
)
```

#### 预设话术（Canned Responses）

工具还可以返回完整的预设话术（canned responses）以供考虑，以及用于在预设话术渲染期间进行替换的字段。有关预设话术属性的更多信息，请参阅[预设话术](https://parlant.io/docs/concepts/customization/canned-responses)章节。

## 基于工具结果的指南重新评估

在某些情况下，工具结果会影响哪些指南变得相关。以下是一个示例：

考虑一个处理转账的银行智能体。当用户请求转账时，一条条件为"用户想要转账"的指南会激活 `get_user_account_balance()` 工具以检查可用资金。该工具返回当前余额，随后可以基于其返回值触发额外的指南匹配。

例如，如果余额低于 500 美元，我们可能让一条"余额不足"指南激活，指示智能体说出类似这样的话：_"我看到您当前的余额较低。您确定要继续这笔转账吗？这笔交易可能会让您面临透支手续费的风险。"_

在 Parlant 中，你可以将某些指南标记为在工具调用后重新评估。这意味着一旦工具被调用，指南匹配器将重新评估会话，以查看是否应根据工具结果激活任何新指南——在运行工具*之后*、生成响应*之前*。

你可以这样做：

```python
# The agent will ensure to reevaluate this guideline after running this tool
await guideline.reevaluate_after(my_tool)
```

## 最佳实践

#### 关于自然语言编程的一点说明

尽管 LLM 擅长对话式任务，但它们在复杂逻辑运算和多步骤规划方面仍很吃力。近期对 LLM 架构的研究表明，即便是先进模型也难以进行一致的逻辑推理和顺序决策。LLM 中的"规划问题"——将复杂任务分解为有序步骤并综合得出结论——在需要大规模保持一致时，仍然是一个重大的未解难题。

鉴于这些局限，Parlant 采取一种务实的做法：将代码中的逻辑与行为建模分离。Parlant 不鼓励将业务逻辑嵌入指南，而是鼓励在对话行为与底层业务操作之间保持清晰的分离。

将你的工具视为存放确定性、程序化业务逻辑的地方，而将指南视为你的对话界面设计。这种分离会产生更清晰、更易维护、更可靠的系统。

> **智能体式 API 设计（Agentic API Design）**
>
> 要了解关于设计智能体工具的更多最佳实践，我们推荐阅读我们的博客文章 [Agentic Backends](https://parlant.io/blog/what-no-one-tells-you-about-agentic-api-design)。

#### 示例

**1. 电商产品推荐：**

不要这样做

指南中包含复杂业务逻辑，过度依赖 LLM
> * **指南动作：**
> 如果用户提到运动，则查看其购买历史。
> 如果他们买过跑步装备，则推荐高端跑鞋。
> 如果他们是新用户，则推荐入门套装。
> * **工具关联：** `[get_product_catalog]`

应当这样做

逻辑放在编码的推荐引擎中，这才是它该去的地方

> * **指南动作：** 提供个性化推荐
> * **工具关联：** `[get_personalized_recommendations]`

**2. 财务咨询：**

不要这样做

财务分析逻辑依赖不可靠的 LLM 数值理解能力
> * **指南动作：** 检查账户余额和最近交易。
>           如果支出超过通常模式的 80%，则建议进行预算审查。
>           如果投资回报下降，则建议调整投资组合。
> * **工具关联：** `[get_account_data]`

应当这样做

财务分析逻辑由代码可靠地处理

> * **指南动作：** 获取个性化财务洞察
> * **工具关联：** `[get_financial_insights]`

## 工具上下文（ToolContext）

`ToolContext` 参数是一个特殊对象，它为工具提供上下文信息和实用工具。

让我们看看 `ToolContext` 中一些最有用的属性和方法：

1. `agent_id`：正在调用该工具的智能体的唯一标识符。
2. `customer_id`：与智能体交互的客户的唯一标识符。
3. `session_id`：当前会话的唯一标识符。
4. `emit_message(message: str)`：向客户发回消息的方法。可用于在长时间运行的工具调用期间报告进度。
5. `emit_status(status: p.SessionStatus)`：更新[会话状态](https://parlant.io/docs/concepts/sessions#status-event)的方法。

#### 访问服务器对象（智能体、客户等）

你还可以从 `ToolContext` 访问服务器对象，从而访问你的智能体、指南以及其他服务器级别的资源。

要访问服务器对象，可以按如下方式使用 `p.ToolContextAccessor`：

```python
import parlant.sdk as p

@p.tool
async def my_tool(context: p.ToolContext) -> p.ToolResult:
    server = p.ToolContextAccessor(context).server

    # Access the current agent using the agent_id from the context
    agent = await server.get_agent(id=context.agent_id)

    # Access the current customer
    customer = await server.get_customer(id=context.customer_id)

    # ...

    return p.ToolResult(...)
```

#### 安全的数据访问

假设你需要构建一个工具，用于检索或展示属于不同客户的私有数据。

一种朴素的做法是要求客户表明自己的身份，并将其作为访问正确数据的令牌。但这种方式极不安全，因为它依赖 LLM 来识别用户。LLM 可能会识别错误，更糟的是，还可能被恶意用户操纵。

一种更好、更可靠的做法是向 Parlant [注册你的客户](https://parlant.io/docs/concepts/entities/customers#registering-customers)，并以编程方式使用包含在工具 `ToolContext` 参数中的信息。

实际写法如下：

```python
@p.tool
async def get_transactions(context: p.ToolContext) -> p.ToolResult:
    transactions = await DB.get_transactions(context.customer_id)
    return p.ToolResult(transactions)
```

## 工具洞察（Tool Insights）与参数选项

由于 Parlant 的架构极度模块化，指南匹配、工具调用和消息撰写等组件彼此独立运行。虽然这种非单体式的方法在管理其复杂的语义逻辑方面带来诸多优势，但它也要求在这些组件之间传递上下文感知。

**工具洞察（Tool Insights）** 是工具调用与消息撰写之间的桥接组件，确保当工具因某种原因（例如缺少必需参数）而无法被调用时，撰写组件能够知晓这一情况。

这使得智能体能够更智能地响应。例如，如果它不知道某个合适的工具何时无法被调用，它可能会生成具有误导性的响应。但借助工具洞察，智能体能够识别缺失的信息，并在需要时自动向客户询问所需的工具参数。

#### 工具参数选项（ToolParameterOptions）

为了让你能够增强工具洞察的基础行为，你可以使用 **ToolParameterOptions**，一种特殊的参数注解，它为工具参数的处理和传达方式增加了更多控制。

工具洞察帮助智能体识别工具调用何时以及为何失败，而 **ToolParameterOptions** 则更进一步，引导智能体在何时以及如何解释特定的缺失参数。

```python
from typing import Annotated
import parlant.sdk as p

@p.tool
async def transfer_money(
  context: p.ToolContext,
  amount: Annotated[float, p.ToolParameterOptions(
    source="customer",  # Only the customer can provide this value - the agent cannot infer it
  )],
  recipient: Annotated[str, p.ToolParameterOptions(
    source="customer",
  )]
) -> ToolResult:
    # ...
```

**ToolParameterOptions** 由若干个可选参数组成，每个参数都细化智能体对该参数的理解和应用：

- `hidden`：如果设为 `True`，该参数将不会被暴露给消息撰写。这意味着当该参数缺失时，智能体不会通知客户。它通常用于内部参数，例如不透明的产品 ID，或任何应当留在幕后的信息。

- `precedence`：当一个工具有多个必需参数时，传递给客户的工具洞察可能会让人不堪重负（例如在一条消息中索要 5 个不同的条目）。precedence 允许你创建分组（共享相同值的组），使客户一次只会了解到其中的几个（共享同一 precedence 值的那些）——并且按照你选择的顺序。

- `source`：定义参数的来源。智能体应当直接从客户那里请求该值（"customer"），还是应当从周围上下文推断（"context"）？如果未指定，默认为 "any"，意味着智能体可以从任何地方获取它。

- `description`：帮助智能体在从上下文中提取参数值（argument）时正确解读该参数。如果参数名含糊或不清楚，请填写此项。

- `significance`：面向客户的一段描述，说明为什么需要该参数。这有助于客户理解并认同他们需要提供什么信息以及为什么。

- `examples`：一组示例值，说明应如何提取参数值。这对于强制格式很有用（例如 "YYYY-MM-DD" 这样的日期格式）。

- `adapter`：一个函数，在将推断出的值传递给工具之前，将其转换为正确的类型。如果提供，智能体会让提取出的参数值经过该函数，以确保其符合预期格式。当参数类型是你代码库中的自定义类型时使用。

- `choice_provider`：一个为参数值提供有效选项的函数。使用它来约束智能体，使其从该函数所返回的特定集合中动态选择一个值。

## 参数值约束

当你需要工具的参数值落入一组特定的选项时，Parlant 可以帮助你确保工具调用按照这些选项进行参数化。有三种方式可以做到：

1. 当你能够提供硬编码的选项时，使用枚举（enum）
1. 当选项是动态的（例如特定于客户）时，使用 `choice_provider`
1. 当参数遵循更复杂的结构时，使用 Pydantic 模型

#### 枚举参数

使用 `Enum` 类指定一组提前已知的固定选项。

```python
import enum

class ProductCategory(enum.Enum):
  LAPTOPS = "laptops"
  PERIPHERALS = "peripherals"
  MONITORS = "monitors"

@p.tool
async def get_products(
  context: p.ToolContext,
  category: ProductCategory,
) -> p.ToolResult:
  # your code here
  return p.ToolResult(returned_data)
```

#### 选项提供器（Choice Provider）

基于当前执行上下文动态提供一组选项。

```python
async def get_last_order_ids(context: p.ToolContext) -> list[str]:
  return await load_last_order_ids_from_db(customer_id=context.customer_id)

@p.tool
async def load_order(
  context: p.ToolContext,
  order_id: Annotated[Optional[str], p.ToolParameterOptions(
    choice_provider=get_last_order_ids,
  )],
) -> p.ToolResult:
  # your code here
  return p.ToolResult({...})
```

#### Pydantic 模型

使用 Pydantic 模型为参数定义一个复杂的结构，该结构可以包含校验和约束。

```python
from pydantic import BaseModel

class ProductSearchQuery(BaseModel):
  category: str
  price_range: tuple[float, float]

@p.tool
async def search_products(
  context: p.ToolContext,
  query: ProductSearchQuery,
) -> p.ToolResult:
  # your code here
```