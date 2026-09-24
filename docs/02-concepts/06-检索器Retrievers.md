> 来源：docs/concepts/customization/retrievers.md，Parlant v3.3.1 官方英文文档中文翻译。

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