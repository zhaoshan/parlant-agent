> 来源：docs/concepts/entities/agents.md，Parlant v3.3.1 官方英文文档中文翻译。

> **⚠️ 官网更新注记（2026-09-30 核对，以 https://www.parlant.io/docs/concepts/entities/agents 为准）**
> 本译文为本地 parlant 仓库 docs/ 的 v3.3.1 快照，官网已更新；经 parlant 源码溯源，
> 下述差异多数为「v3.3.1 代码已支持、仅文档过时」，已按官网回改正文：
> - 回改项：`server.agents.create` → `server.create_agent`（源码 sdk.py 有 create_agent）；新增 自定义 ID（Custom IDs，`server.create_agent(id=...)`，默认由 description 自动生成 id、改 description 会破坏会话关联）/ 输出模式（Output Modes，p.MessageOutputMode BLOCK·STREAM，STREAM 仅 FLUID 组合模式、canned response 恒 block）/ 智能体之间转接（Transferring Between Agents，`p.Session.current.update(agent=...)` / `client.sessions.update(agent_id=...)`）/ 主动消息（agent.utter()）/ 前导配置（Preamble Configuration，preamble_config）；明确「所有行为配置——指南/旅程/工具/术语表——均作用域于智能体」
> - 官网新增、未全文重写项：管理多主题上下文（Managing Multi-topic Context）论述、动态前导指令（get_instructions），完整见官网对应页
> - 源码未确认项：无（本页所列 API 均已溯源确认）

# 智能体 (Agent)

在 Parlant 中，智能体 (Agent) 是一个经过定制的 AI 人格，以单一、能干的实体身份与客户互动。它本质上是"你所交谈的对象"，不同于某些框架中智能体是一个专门的任务函数 (task function)。

智能体构成了对话自定义的基本伞状结构——**所有的行为配置——指南、旅程、工具、术语表——都作用域于智能体（scoped to an agent）**。

```python
import parlant.sdk as p

async with p.Server() as server:
    hexon = await server.create_agent(
        name="Hexon",
        description="Technical support specialist"
    )

    # Continue to model the agent's behavior using guidelines, journeys, etc....
```

> **注意：**
>
> 请注意，单个 Parlant 服务器可以托管**无限数量**的智能体，每个智能体都拥有不同的角色和人格。

### 管理多主题上下文（Managing Multi-topic Context）

与基于图（graph）的框架不同——在那里智能体是一个专门的任务节点——Parlant 遵循一种更简单的建模立场：智能体是一个完整的对话实体，拥有自己的身份、行为规则和工具。

关于[多智能体系统失败](https://arxiv.org/abs/2503.13657)的研究表明，拆分成多个智能体往往会引入协调和一致性问题，其代价超过了局部的模块化收益。

在 Parlant 中，你无需使用子智能体来管理不同的主题或任务。相反，单个智能体会在对话的每个时刻动态装配正确的上下文：应用相关的指南，并按需调用适当的工具。

每个智能体都可以针对其目标用户，独特地配置自己的风格、气质和交互模式。更重要的是，不同的业务部门可以分别拥有并维护各自的智能体。例如：
* IT 部门管理 **Hexon**
* 客户成功团队负责 **Sprocket**
* 销售/市场部门控制 **Piston**

这种以智能体为基础的设计，在 Parlant 内为关注点分离 (separation of concerns) 创造了天然的边界。

### 塑造智能体的身份（Crafting Identity）
想象你正在招聘一位新员工，他将成为你服务的代言人。正如你会仔细考量一位人类雇员的性格与处事方式一样，塑造一个智能体的身份，最终也需要对其核心特质进行审慎的思考——而且，就像任何一位出色的雇员一样，你可以根据真实世界的反馈来培养和调整它。

一个智能体的 `description` 设置了它总体的人格与语气。先从简单的描述开始，再根据真实交互逐步精炼。举一个例子，让我们跟随我们的技术支持专员 **Hexon** 可能的演变过程。在其第一版迭代中，我们可能只是把它定义为"一个帮助用户专业、高效地解决技术问题的技术支持智能体"。在观察了一些交互之后，我们可能会发现它显得过于机械，无法与用户建立信任。

于是我们精炼它的身份：

> "一位将深厚技术知识与耐心讲解相结合的技术支持专员。你以让复杂概念易于理解又不至于过度简化为荣。你始终专业，却以温暖、平易近人的语气沟通。你相信每一个技术问题都是帮助用户更好地理解其工具的机会。当用户感到沮丧时，你保持冷静和同理心，认可他们所面临的困难，同时专注于解决方案。"

随着我们观察更多的交互，我们可能会进一步精炼这个总体身份。也许我们会发现当 Hexon 展现出更多个性时用户反应更好，或者我们发现某些技术讨论需要更多庄重感。身份可以随着这些洞见而演变。

关键在于，先从一个能为智能体提供基本定位的身份开始，但要对基于真实交互的调整保持开放。观察用户对智能体举止的反应。收集利益相关者的反馈。相应地调整身份。

`description` 为智能体提供了总体、基准性的定位。它*始终*包含在智能体的上下文中。对于按情境适用的具体行为规则——何时追加销售、如何处理投诉、在敏感时刻该说什么——请使用[指南](/docs/concepts/customization/guidelines)和[预设话术](/docs/concepts/customization/canned-responses)，它们参与上下文过滤。

### 自定义 ID（Custom IDs）

默认情况下，为方便起见，Parlant 会根据 description 自动生成智能体 ID。这对开发很方便，但意味着**修改 description 会破坏会话关联**。对于生产环境，请使用硬编码的 ID：

```python
hexon = await server.create_agent(
    id="hexon",  # Stable across description changes and deployments
    name="Hexon",
    description="Technical support specialist",
)
```

### 单个智能体，还是多个智能体？
关于应该把面向用户的智能体建模为单智能体还是多智能体系统，一直存在争论。Parlant 的立场是两者兼而有之。

一般而言，当我们的解决方案对真实世界进行建模时，管理复杂度会更容易，因为这让我们自然而然地拥有多得多的数据来对设计决策进行推理，而不是试图凭空想出一些牵强的东西。所以，与其问一个非常根本的问题："用户应该如何与这个智能体互动？"，我们不如问一个更有成效的问题，比如："基于用户的真实生活经验，他们会期望什么？"

在实践中，当我们与人类客服互动时，我们对这种体验已经有了一些既定的期望：
- 如果我们正在与一位智能体交谈，它拥有我们对话的完整上下文。它是连贯的。它不会突然忘记，或出乎意料地改变对局势的理解。
- 我们正在交谈的这位智能体，未必总能帮我们解决所有问题。我们可能需要被转接给另一位专精于某个主题的智能体。
- 我们期望被告知这种转接。如果转接突然发生，或在我们不知情的情况下发生，我们会把它视为一种草率的客户体验。

你可以看到，来自熟悉的、真实世界使用模式的洞见，如何帮助我们做出明智的设计决策。通过以真实世界模式来建模智能体交互，我们不仅能更好地理解应该追求怎样的结果，而且事实证明，管理我们智能体的配置也变得更容易推理了。

这就是为什么 Parlant 的正式建议是：**按照人类智能体的工作方式对 AI 智能体进行建模**。换句话说，如果你能在一个真实世界的用例中看到一个单一的人格，那就意味着在 Parlant 中它应该被表示为一个单一的 AI 智能体。由于 Parlant 会在每一轮只动态匹配相关的指南，单个智能体完全可以处理复杂、多主题的对话而不失焦——你无需为了管理复杂度而拆分成多个智能体，框架会替你处理这些。

当你*确实*需要专业化时（例如从销售转接到计费），Parlant 支持明确的智能体转接，它能够保留对话历史，并且对用户而言感觉自然。

> **提示：多智能体系统的失败**
>
> 有一篇很有意思的论文讨论[多智能体系统的失败之处](https://arxiv.org/abs/2503.13657#:~:text=We%20present%20MAST%20%28Multi-Agent%20System%20Failure%20Taxonomy%29%2C%20the,over%20200%20tasks%2C%20involving%20six%20expert%20human%20annotators)，尽管这类系统承诺了模块化和专业化。它强调了多智能体系统常常在协调、沟通和一致性上苦苦挣扎，从而引发意外行为和失败。这与 Parlant 采用单一智能体来维持对话中连贯性与上下文的做法是一致的。

### 输出模式（Output Modes）

默认情况下，Parlant 以单个块（block）的形式投递响应。对于较长的响应或语音智能体，流式（streaming）可以让文本随生成过程逐步显现：

| 模式 | 行为 | 最适合 |
| --- | --- | --- |
| `BLOCK` | 一次性发送完整消息（默认） | 短回复、严格组合（composition） |
| `STREAM` | 按生成过程逐 token 流式输出 | 较长回复、语音智能体 |

```python
agent = await server.create_agent(
    name="Hexon",
    description="Technical support specialist",
    output_mode=p.OutputMode.STREAM,
)
```

流式只改变投递机制。指南匹配、工具调用和上下文装配都以相同方式工作——只有最终的消息生成是增量流式输出的，而不是缓冲后一次性发送。

> **流式与预设话术**
>
> 流式仅在 `FLUID` 组合模式下受支持。当选择了一条[预设话术 (canned response)](/docs/concepts/customization/canned-responses) 时，无论输出模式设置如何，智能体都会以块（block）形式投递它。

### 智能体之间的转接（Transferring Between Agents）

要把客户转接给另一个智能体，直接更新会话即可。这通常在[工具](/docs/concepts/customization/tools)内部完成，使转接可以基于对话上下文自动发生：

```python
billing_agent = await p.Server.current.get_agent(id="billing_specialist")

await p.Session.current.update(agent=billing_agent)

return p.ToolResult(data="Transferring you to our billing specialist")
# 后续响应将由计费专家智能体发出
```

你也可以通过客户端 SDK 从外部系统完成转接：

```python
from parlant.client import ParlantClient

client = ParlantClient(PARLANT_SERVER_URL)

client.sessions.update(
    session_id=SESSION_ID,
    agent_id="billing_specialist"
)
```

### 主动消息（Proactive Messages）

智能体还可以使用 `agent.utter()` 主动将消息发送进会话——例如，在后台操作完成后跟进，或在客户闲置时主动询问。

参见[触发式响应（Triggered Responses）](https://www.parlant.io/docs/advanced/triggered-responses)了解更多。

### 前导配置（Preamble Configuration）

当 Parlant 匹配指南、调用工具并生成回复时，它会发送一段简短的确认——即**前导（preamble）**——以让对话保持自然和响应性。

可以把它想成人类客服在查找资料时会说的"好的，让我查一下"。

默认情况下，Parlant 从诸如 "Hey there" 和 "Let me check that for you" 之类的通用前导中挑选，但你可以为每个智能体定制这些前导：

```python
agent = await server.create_agent(
    name="Hexon",
    description="Technical support specialist",
    preamble_config=p.PreambleConfiguration(
        examples=["One moment, please.", "Let me look into that.", "Checking now."],
    ),
)
```

`examples` 字段会替换该智能体的默认前导集合。

#### 动态前导指令（Dynamic Preamble Instructions）

如需更多控制，提供一个 `get_instructions` 可调用对象，它返回用于前导生成的上下文指令：

```python
async def preamble_instruction_provider(ctx: p.EngineContext) -> Sequence[str]:
    instructions = []

    hour = datetime.now().hour
    if hour < 12:
        instructions.append("Use a morning greeting like 'Good morning'")
    elif hour >= 18:
        instructions.append("Use an evening greeting like 'Good evening'")

    return instructions

agent = await server.create_agent(
    name="Hexon",
    description="Technical support specialist",
    preamble_config=p.PreambleConfiguration(
        examples=["One moment, please", "Let me look into that", "Good morning"],
        get_instructions=preamble_instruction_provider,
    ),
)
```
