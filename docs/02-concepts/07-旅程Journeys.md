> 来源：concepts/customization/journeys.md，Parlant v3.3.1 官方英文文档中文翻译。

# 旅程（Journeys）

有很多使用场景，你希望你的智能体跟随一段特定的对话流程，例如预订旅行、排查某个问题，或以其他方式以预期的方式引导用户完成一个对话流程。

在 Parlant 中，这可以借助**旅程（Journeys）**轻松且可靠地实现。

#### 旅程的结构（Journey Structure）

旅程有 4 个重要组成部分：
1. **标题（Title）：** 一个简短、描述性的名称，用于将旅程与其他旅程区分开来。
1. **条件（Conditions）：** 这些上下文查询（contextual queries）决定了旅程应在何时处于激活状态。
1. **描述（Description）：** 它让你能够描述旅程的性质，在需要时也可以包含一些动机说明或定位说明。
1. **状态与转移（States & Transitions）：** 一个状态图（state diagram），向智能体传达理想的流程是什么。

> **在严格性与灵活性之间取得平衡（Balancing Rigidity vs. Flexibility）**
>
> 在传统的对话框架中，流程是被严格定义的，每个状态和转移都必须被逐字逐句地严格遵循。
>
> 虽然这种方式易于理解和实现，但当智能体无法适应客户的交互模式时，往往会导致令人沮丧的用户体验。这种"一刀切"的方法没有考虑到人类对话的细微差别——从而导致用户失去参与感和满意度，最终导致智能体被闲置。
>
> Parlant 实现了一种"汲取经验教训"（lessons learned）的方法，允许智能体以更自然的方式在旅程的状态之间穿行。它们可以选择跳过状态、重新访问先前的状态，甚至以自适应的方式跳转到后续的状态。
>
> 因此，旅程并不旨在被严格遵循，而是作为智能体的指导框架（guiding framework）。智能体将尽可能严格地遵循流程，同时仍然对客户的交互模式保持自适应的方式。

## 一个完整示例（A Worked Example）

考虑以下旅行社智能体中的一个旅程示例：
> * **标题：** 预订航班（Book Flight）
> * **条件：** 客户请求预订航班
> * **描述：** 此旅程引导客户完成航班预订流程。

```mermaid
%%{init: { "theme": "forest" }}%%
stateDiagram-v2
    direction LR
    state "Where to?" as A
    state "Dates?" as B
    state "Load destinations" as Ca
    state "Suggest" as Cb
    state "Confirm" as E
    state "Book" as F
    state "Provide ticket" as G
    [*] --> A
    A --> Ca: Don't know
    Ca --> Cb
    A --> B: Destination provided
    Cb --> B: Destination selected
    B --> E
    E --> F: Yes
    E --> [*]: No
    F --> G
    G --> [*]

    style Ca fill:#ffeecc,stroke:#333,stroke-width:1px
    style F fill:#ffeecc,stroke:#333,stroke-width:1px
```

当客户要求预订航班时，此旅程将被激活。然后，智能体将努力遵循流程，同时以符合客户节奏的自适应方式行进，同时确保收集到所有必要的信息。

#### 实现该旅程（Implementing the Journey）
在我们进一步了解旅程的工作原理之前，先看看如何实现上面的旅程：

```python
async def create_book_flight_journey(agent: p.Agent):
    journey = await agent.create_journey(
        title="Book Flight",
        conditions=["The customer requested to book a flight"],
        description="This journey guides the customer through the flight booking process.",
    )

    t1 = await journey.initial_state.transition_to(chat_state="Ask if they have a destination in mind")

    #  Branch out based on the customer's response
    t2 = await t1.target.transition_to(condition="They do", chat_state="Get dates of travel")

    t3a = await t1.target.transition_to(condition="They don't", tool_state=load_popular_destinations)
    t3b = await t3a.target.transition_to(chat_state="Recommend a destination")

    # Merge back to the main path after choosing a destination.
    # This is done by transitioning into an existing state node.
    await t3b.target.transition_to(state=t2.target, condition="Destination selected")

    t4 = await t2.target.transition_to(chat_state="Confirm details")

    t5a = await t4.target.transition_to(tool_state=book_flight)
    t5b = await t5a.target.transition_to(chat_state="Provide ticket details")
```

## 状态与转移（States and Transitions）
旅程是仿照状态图（state diagram）建模的，状态图是一个有向图（directed graph），其中每个节点代表一个**状态（state）**，每条边代表一个**转移（transition）**（转移可能与一个条件相关联）。

```mermaid
stateDiagram-v2
    direction LR
    state "CHAT STATE" as A
    state "TOOL STATE" as B
    state "CHAT STATE" as C
    state "CHAT STATE" as D
    state "FORK STATE" as E
    state "CHAT STATE" as F
    state "CHAT STATE" as G

    [*] --> A: INITIAL
    A --> B: CONDITIONAL
    A --> C: CONDITIONAL
    B --> D: DIRECT
    C --> E: DIRECT
    D --> E: DIRECT
    E --> F: CONDITIONAL
    E --> G: CONDITIONAL
    F --> [*]: END
    G --> [*]: END

    style B fill:#ffeecc,stroke:#333,stroke-width:1px
```

#### 状态（States）
1. **聊天状态（Chat States）：** 处于此状态时，智能体将在该状态动作（action）的指导下与客户聊天。智能体可能在此状态中停留多个轮次，直到它决定转移到另一个状态。
```python
t = await state.transition_to(chat_state=CONVERSATIONAL_INSTRUCTION)
```
2. **工具状态（Tool States）：** 在此状态中，智能体将调用一个外部工具来执行某项动作，并将其结果加载到上下文中。工具状态之后必须紧跟一个聊天状态，聊天状态通常用于向客户展示工具的结果。
```python
t = await state.transition_to(tool_state=TOOL)
```
```python
t = await state.transition_to(tool_state=TOOL, tool_instruction=OPTIONAL_HINT_ON_HOW_TO_USE_TOOL)
```

> **从工具状态转移到聊天状态（Transitioning from Tool to Chat）**
>
> 当从工具状态转移到聊天状态时，智能体会自动将工具的结果加载到上下文中，因此你可以在聊天状态的动作中使用它。请注意，工具状态不能转移到另一个工具状态；它之后必须始终紧跟一个聊天状态。
>
> 这是有意为之的设计，因为在智能体应用（agentic applications）中，工具的使用会带来可感知的延迟。与其使用连续的工具状态，不如使用单个工具状态来执行所有必要的动作，然后再紧跟一个聊天状态向客户展示结果。

#### 转移（Transitions）
1. **直接转移（Direct Transitions）：** 这些转移应始终被采用。它们在不产生分支的情况下推动对话向前进行。
2. **条件转移（Conditional Transitions）：** 仅当（且每当）其关联的条件被满足时，这些转移才会被采用。
```python
t = await state.transition_to(chat_state=CONVERSATIONAL_INSTRUCTION, condition=CONDITION)
```
```python
t = await state.transition_to(tool_state=TOOL, condition=CONDITION)
```

在大多数情况下，你会使用接受 `chat_state` 或 `tool_state` 参数的 `transition_to()` 重载，它会自动为你创建转移的目标状态。不过，你也可以使用接受 `state` 参数的 `transition_to()` 重载，它允许你转移到旅程中已存在的状态节点。

```python
t = await state.transition_to(state=EXISTING_STATE)
```
```python
t = await state.transition_to(state=EXISTING_STATE, condition=CONDITION)
```

> **组合使用条件转移与直接转移（Combining Conditional and Direct Transitions）**
>
> 如果一个状态有一条指向其他状态的条件转移，那么它就不能同时再有一条从它出发的直接转移。这是因为当条件满足时，引擎将无法在逻辑上确定应该采用哪条转移。SDK 强制执行这一规则。

#### 分叉状态（Fork States）
旅程还支持一种特殊的状态，称为**分叉状态（fork state）**。

在此状态中，智能体将评估条件，并据此对对话流程进行分支。尽管严格来说，这种分支可以不用分叉状态来建模，但它们有时是一种有用的建模工具，用于保持对话流程清晰、明确且有条理。

```python
fork = await state.fork()

t1 = await fork.transition_to(chat_state=CONVERSATIONAL_INSTRUCTION, condition=CONDITION_1)
t2 = await fork.transition_to(chat_state=CONVERSATIONAL_INSTRUCTION, condition=CONDITION_2)
t3 = await fork.transition_to(tool_state=TOOL, condition=CONDITION_3)
```

> **可视化你的旅程（Visualizing Your Journey）**
>
> 在代码中构建状态图有时可能会让人有些困惑。通常有用的做法是，在构建旅程时将其可视化，以确保流程清晰、合乎逻辑且符合你的意图。做法如下：
>
> 1. 在浏览器中访问 `http://localhost:8800/journeys`。
> 2. 复制你希望可视化的旅程的 ID。
> 3. 在浏览器中访问 `http://localhost:8800/journeys/<JOURNEY_ID>/mermaid`，将 `<JOURNEY_ID>` 替换为你复制的 ID。
> 4. 复制生成的 Mermaid 图代码。
> 5. 将其粘贴到 [Mermaid live editor](https://mermaid.live/) 中以可视化该旅程。

## 旅程 vs. 任务自动化（Journey vs. Task Automation）
如果你查看引擎与旅程的协作方式，就会明白旅程不应该被用来指导模型如何自动化执行任务。相反，旅程被智能体用来进行自我定位（self-orientate），并根据你的偏好来引导对话流程。

这是回顾将**业务逻辑（business logic）**与**对话逻辑（conversation logic）**相分离的重要性的好时机。前者最好由自定义的[专用工具（dedicated tools）](https://parlant.io/docs/concepts/customization/tools)来处理（这些工具内部可能使用也可能不使用 LLM），而后者最好由对话引擎来处理。

#### 应该做与不该做的（Do's and Don'ts）

**不该做（DON'T）**

以下是一个***无效***的旅程，因为它代表的不是对话流程，而是一个任务自动化流程。

```mermaid
stateDiagram-v2
    direction LR
    state "Find user ID" as A
    state "Load personal preferences" as B
    state "Send email" as C
    [*] --> A
    A --> B
    B --> C: Email notifications enabled
    B --> [*]: Email notifications disabled

    style A fill:#ffeecc,stroke:#333,stroke-width:1px
    style B fill:#ffeecc,stroke:#333,stroke-width:1px
    style C fill:#ffeecc,stroke:#333,stroke-width:1px

```

**应该做（DO）**

以下是一个有效的旅程，因为它代表了一个引导客户完成某个流程的对话协议（conversation protocol）。

```mermaid
stateDiagram-v2
    direction LR
    state "Ask for order number" as A
    state "Get order details" as B
    state "Process refund" as C
    state "Transfer to human" as D
    [*] --> A
    A --> B
    B --> C: Eligible for refund
    B --> D: Not eligible for refund
    C --> [*]
    D --> [*]

    style B fill:#ffeecc,stroke:#333,stroke-width:1px
```

## 上下文管理（Context Management）

LLM 是一项了不起的创造，它建立在文本的[统计注意力（statistical attention）](https://arxiv.org/abs/1706.03762)原理之上；然而，它们的注意力范围却痛苦地有限。在遵循指令方面，它们需要帮助。

在幕后，Parlant 通过动态管理 LLM 的上下文，使其在每一点上都只包含相关的旅程，从而确保智能体的回应符合预期。

它是使用 `GuidelineMatcher` 来实现这一点的，本质上是将当前对话上下文与相关旅程的条件进行匹配——而这些条件在幕后基本上就是观察性（非操作性）指南（observational (non-actionable) guidelines）。

```mermaid
%%{init: {'sequence': {'mirrorActors': false}}}%%
sequenceDiagram
    participant Engine
    participant GuidelineMatcher
    participant JourneyStore
    participant MessageComposer

    Engine ->> GuidelineMatcher: match guidelines
    GuidelineMatcher -->> Engine: <guidelines>
    Engine ->> JourneyStore: get journeys for matched conditions
    JourneyStore -->> Engine: <journeys>
    Engine ->> GuidelineMatcher: match journey states
    GuidelineMatcher -->> Engine: <journey states>
    Engine ->> MessageComposer: <journey states, guidelines>
    MessageComposer -->> Engine: <well-guided message>
```

在每次回应之前，Parlant 只加载与对话当前状态相关的指南和旅程。这种动态管理将 LLM 的"认知负担（cognitive load）"降至最低，最大化其注意力，从而使每次回应与预期行为的一致性（alignment）达到最大。

> **延迟优化（Latency Optimizations）**
>
> 这种来回（back and forth）的方法被实现为一个最小化响应延迟的优化算法。
>
> 引擎首先尝试基于当前对话上下文预测哪些旅程将被激活。基于这一预测，它尝试与指南匹配并行地匹配相关旅程的状态，从响应延迟中节省数秒钟。
>
> 只有当这一预测失败时（即，当有其他旅程被激活时），它才会产生额外的步骤来匹配这些旅程的状态。

## 旅程作用域的指南（Journey-Scoped Guidelines）

你可以添加旅程作用域的[指南（guidelines）](https://parlant.io/docs/concepts/customization/guidelines)，它们只有在依赖其的旅程也处于激活状态时才会被激活。在所有其他时候，这些指南都会被忽略。

使用旅程作用域的指南，是以深思熟虑的方式处理偏离旅程主流程（digressions）的推荐做法。它还能帮助你维护一个干净、有条理的对话模型，确保某些指南只在其预期上下文中被评估和激活。

> **指令优先级（Instruction Precedence）**
>
> 请注意，一般而言，Parlant 智能体对指南的权重高于对旅程状态的权重，因为指南被视为更具体的行为覆盖（behavioral overrides）。这意味着，如果某条指南被匹配，它往往会优先于处于激活状态的旅程状态。

```python
@p.tool
async def transfer_to_human_agent(context: p.ToolContext) -> p.ToolResult:
    ...

guideline = await journey.create_guideline(
    condition="the customer says they're unable to pay"
    action="connect them with a human agent",
    tools=[transfer_to_human_agent],
),
```

> **了解更多（Learn More）**
>
> 要了解更多关于指南的信息，请查看[指南（Guidelines）](https://parlant.io/docs/concepts/customization/guidelines)页面。

## 旅程作用域的预设话术（Journey-Scoped Canned Responses）
你还可以把预设话术（canned responses）附加到旅程上，将它们作用域限定到这些旅程，使得只有当它们依赖的旅程处于激活状态时，这些预设话术才会被考虑。

```python
await journey.create_canned_response(
    template="What destination are you interested in?",
)

await journey.create_canned_response(
    template="I'm sorry, but I can't assist with that right now. Shall we go on with booking your flight?",
)
```

#### 状态作用域的预设话术（State-Scoped Canned Responses）
你还可以将特定的预设话术与旅程中的特定状态关联起来。

状态作用域的预设话术有两种模式：**显式考虑（Explicit Consideration）**和**独占考虑（Exclusive Consideration）**。

1. **显式考虑：** 在此模式下，智能体将确保当处于该状态时，相关联的回应始终会被纳入选择考虑。这是通过在 `journey` 或 `agent` 对象下创建预设话术来实现的。
```python
await state.transition_to(
    chat_state="Ask if they have a destination in mind",
    canned_responses=[
        await journey.create_canned_response(
            template="What destination are you interested in?",
        ),
    ],
)
```
2. **独占考虑：** 在此模式下，智能体在该状态时只会考虑相关联的回应。在其他任何时间它都不会使用这些回应。这是通过在 `server` 对象下创建预设话术来实现的。

```python
await state.transition_to(
    chat_state="Ask if they have a destination in mind",
    canned_responses=[
        await server.create_canned_response(
            template="What destination are you interested in?",
        ),
    ],
)
```

> **了解更多（Learn More）**
>
> 要了解更多关于预设话术的信息，请查看[预设话术（Canned Responses）](https://parlant.io/docs/concepts/customization/canned-responses)页面。