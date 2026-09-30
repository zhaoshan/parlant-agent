> 来源：docs/concepts/customization/retrievers.md，Parlant v3.3.1 官方英文文档中文翻译。
>
> **⚠️ 官网更新注记（2026-09-30 核对，以 https://www.parlant.io/docs/concepts/customization/retrievers 为准）**
> 本译文为本地 parlant 仓库 docs/ 的 v3.3.1 快照，官网已更新；经 parlant 源码溯源，
> 下述差异多数为「v3.3.1 代码已支持、仅文档过时」，已按官网回改正文：
> - 官网新增、未全文重写项：Deferred Retrievers（延迟检索器）/ Scoped Retrievers（作用域检索器）（完整见官网对应页）

# 检索器（Retrievers）

出于务实的原因，Parlant 区分了两种数据访问模式，即工具与**检索器（retrievers）**。

在开发面向客户的智能体时，获取数据实际上有两种不同的用例：
1. **工具**：响应特定事件（例如用户请求），从特定服务获取数据。
2. **检索器**：获取上下文信息，使智能体的知识库围绕当前对话状态进行锚定（ground）、定位和校准。这传统上被称为 RAG（检索增强生成，Retrieval-Augmented Generation）。

一个经验法则是：对于你通常期望智能体"应当已经知道"的数据，使用**检索器**；而工具则用于智能体需要"加载"或"对其进行操作"的数据。

**检索器的用例包括：**
- 获取常见问题的答案
- 基于当前对话上下文获取相关文档或信息
- 获取特定于用户的数据，以个性化智能体的响应（另见[变量](https://parlant.io/docs/concepts/customization/variables)）

> **提示：响应延迟的权衡**
>
> 由于检索器仅用于在当前对话上下文中锚定智能体的知识，它们通常可以与智能体的其他任务（例如指南匹配、工具调用等）并行执行。
>
> 因此，使用检索器可以让你在不增加指南匹配或工具调用延迟的情况下锚定智能体的响应。

## 创建检索器

检索器是一个函数，它接收 `p.RetrieverContext` 并返回 `p.RetrieverResult`。`p.RetrieverContext` 包含当前对话上下文，而 `p.RetrieverResult` 包含检索器已获取的数据。

```python
async def my_retriever(context: p.RetrieverContext) -> p.RetrieverResult:
  ...
```

#### 简单的 RAG 示例

下面是一个简单的检索器示例，它根据客户的最后一条消息从数据库中获取文档：

```python
async def answer_retriever(context: p.RetrieverContext) -> p.RetrieverResult:
    # Get the last message from the conversation
    if last_message := context.interaction.last_customer_message:
        # Use an embedder to convert the message into a vector
        message_vector = my_embedder.embed(last_message.content)
        # Fetch documents from the database based on the message vector
        documents = await fetch_documents_from_db(message_vector)

        return p.RetrieverResult(documents)

    return p.RetrieverResult(None)
```

或者，你可以使用一个 LLM 基于整段交互历史生成查询：

```python
async def answer_retriever(context: p.RetrieverContext) -> p.RetrieverResult:
    if context.interaction.messages:
        # Join all messages in the conversation to create a neat context
        conversation_text = "\n".join(str(msg) for msg in context.interaction.messages)

        # Use an LLM to extract a user query from the conversation
        if query := await my_llm.extract_user_query_from_conversation(conversation_text):
          # Use an embedder to convert the query into a vector
          message_vector = my_embedder.embed(query)
          # Fetch documents from the database based on the query vector
          documents = await fetch_documents_from_db(message_vector)

          return p.RetrieverResult(documents)

    return p.RetrieverResult(None)
```

#### 挂载检索器

要真正让智能体使用你的检索器，你需要按如下方式挂载它：

```python
await agent.attach_retriever(my_retriever)
```

你还可以指定检索器的 ID，这对于调试和日志记录很有用：

```python
await agent.attach_retriever(my_retriever, id="my_retriever")
```

## 检索器结果的存续期

检索器结果的存续期仅限于当前响应；换句话说，它不会在整段对话中持续存在。这也有助于你保持对话上下文的干净和聚焦，同时在整段对话中减少平均输入 token。

## 检索器上下文

使用检索器上下文，你可以访问许多有用的属性，帮助你构建更复杂的检索器：

- `server`：当前正在处理检索器请求的服务器，可用于访问服务器特定的资源或配置。
- `container`：当前正在使用的依赖注入容器，它允许你访问在该容器中注册的服务和资源。
- `logger`：当前正在使用的日志记录器，可用于在检索器执行期间记录调试信息或错误。
- `trace_id`：智能体当前响应的唯一标识符，可用于追踪和调试。
- `interaction`：当前交互，包含对话历史和其他相关信息。
- `agent`：当前正在处理该交互的智能体。
- `customer`：当前正在与智能体交互的客户。
- `variables`：当前为该交互设置的变量。

## 延迟检索器（Deferred Retrievers）

默认情况下，检索器在请求处理的早期阶段（当消息被确认时）运行，与指南匹配并行。这对延迟很友好，但有时你想根据实际匹配到了哪些指南来决定是否包含检索结果。

**延迟检索器（deferred retrievers）** 通过让你返回一个可调用对象（callable）而不是直接结果来解决这个问题。这个可调用对象会在稍后、就在消息生成之前，以完整的引擎上下文（包括所有已匹配的指南）被调用。

你可能会问，为什么要选择不返回检索结果？主要是为了避免用不相关的信息塞满上下文，从而迷惑智能体。

```python
async def conditional_retriever(ctx: p.RetrieverContext) -> p.DeferredRetriever:
    # 这在早期阶段运行，与指南匹配并行
    documents = await fetch_documents(ctx.interaction.last_customer_message)

    async def deferred(engine_ctx: p.EngineContext) -> p.RetrieverResult | None:
        # 检查是否匹配到了特定指南
        matched_ids = {g.id for g in engine_ctx.state.guidelines}

        if MY_GUIDELINE_ID in matched_ids:
            return p.RetrieverResult(data=documents)

        # 返回 None 以跳过添加任何数据
        return None

    return deferred

await agent.attach_retriever(conditional_retriever)
```

这种模式让你兼得两方面的好处：

- **并行执行**：检索工作（例如向量搜索、数据库查询）与指南匹配并行运行，避免额外延迟
- **上下文感知的过滤**：是否包含结果的最终决定，发生在你知道哪些指南已匹配之后

## 作用域检索器（Scoped Retrievers）

智能体级（Agent-level）的检索器在每次交互时都会运行，当数据具有广泛用途时这很合适。但在实践中，这可能导致不必要的上下文污染——在重置密码时拉取了定价文档，在账单咨询时加载了故障排查文章。

相反，你可以将检索器作用域限定到特定的[指南](https://parlant.io/docs/concepts/customization/guidelines)或[旅程](https://parlant.io/docs/concepts/customization/journeys)上。作用域检索器只在其关联实体匹配时才会激活：

#### 指南检索器（Guideline Retrievers）

```python
async def fetch_pricing_docs(ctx: p.RetrieverContext) -> p.RetrieverResult:
    docs = await pricing_db.search(
        ctx.customer.id,
        ctx.interaction.last_customer_message
    )

    return p.RetrieverResult(data=docs)

pricing_guideline = await agent.create_guideline(
    condition="Customer asks about pricing",
    action="Provide pricing based on their plan",
)

# 此检索器只在定价指南匹配时运行
await pricing_guideline.attach_retriever(fetch_pricing_docs)
```

如果定价指南没有匹配，定价文档就不会被获取——保持上下文窗口干净。

#### 旅程检索器（Journey Retrievers）

旅程也是如此。旅程检索器只在旅程激活时运行：

```python
support_journey = await agent.create_journey(
    title="Technical Support",
    description="Handles technical issues",
    conditions=["Customer reports a technical problem"],
)

# 此检索器只在旅程激活时运行
await support_journey.attach_retriever(fetch_troubleshooting_docs)
```

#### 旅程状态检索器（Journey State Retrievers）

你甚至可以将检索器作用域限定到单个旅程状态。当旅程中的特定步骤需要不同的数据时，这很有用：

```python
payment_step = await state.transition_to(
    chat_state="Collect payment details",
)

# 此检索器只在特定状态激活时运行
await payment_step.target.attach_retriever(fetch_payment_options)
```

#### 何时使用哪种（When to Use Which）

有一点需要注意：智能体级检索器与指南匹配并行运行，所以如果检索器在匹配完成之前就结束了，你不会付出任何额外延迟。

相比之下，作用域检索器依赖于知道哪些指南和旅程已匹配——所以它们在匹配完成*之后*才运行。在大多数情况下，这种便利性和精确性是值得的，但如果检索延迟是一个顾虑，带延迟过滤（deferred filtering）的智能体级检索器仍然是更快的方法，尽管实现起来更复杂。

总的来说，作用域检索器是将锚定数据（grounding data）引入智能体上下文的**更受青睐且更方便**的方式。当数据在许多指南中具有广泛用途，或者你需要优化延迟时，使用智能体级检索器。