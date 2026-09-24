> 来源：concepts/customization/glossary.md，Parlant v3.3.1 官方英文文档中文翻译。

# 术语表（Glossary）

术语表是塑造你的智能体对其领域理解的基础部分。它就像你智能体的专业词典：一组特定于你的业务或服务上下文的术语。

### 何时使用术语表（When to Use the Glossary）
当你创建一个智能体来处理特定任务时，它常常需要理解你所在领域的独特词汇。例如，如果你的智能体帮助客人在 Boogie Nights 酒店预订房间，它就需要知道 "Boogie Nights" 在你上下文中意味着什么——在这种情况下，它不仅仅是一部电影的名字，而是你酒店的名字。

#### 创建术语表词条（Creating Glossary Terms）
以下是创建一个新的术语表词条的方法：

```python
await agent.create_term(
    name=TERM,
    description=DESCRIPTION,
    synonyms=[SYNONYM_1, SYNONYM_2, ...],
)
```


### 词条的结构（Structure of Terms）
每个术语表条目由三个部分组成：

> * **术语（Term）：** 被定义的词或短语
> * **描述（Description）：** 该术语在你的特定上下文中是什么意思
> * **同义词（Synonyms）：** 用户可能用来指代该术语的其他说法

例如：
```python
await agent.create_term(
    name="Boogie Nights",
    description="Our luxury beachfront hotel located in Miami",
    synonyms=["BN Hotel", "The Boogie", "Boogie Hotel"],
)
```

### 智能体如何使用术语表（How Agents Use the Glossary）
术语表在智能体交互中起到两个至关重要的作用。

首先，它帮助你的智能体在与客户互动时更好地理解客户。当一位客人说 _"I'd like to stay at The Boogie,"_ 时，智能体知道他们指的是你的酒店。

其次，它帮助智能体正确地解读你的指南。考虑以下配置：

```python
await agent.create_guideline(
    condition="the user asks about Ocean View rooms",
    action="explain the Sunrise Package benefits",
)

await agent.create_term(
    name="Ocean View",
    description="Our premium rooms on floors 15-20 facing the Atlantic",
    synonyms=["seaside rooms", "beach view"],
)

await agent.create_term(
    name="Sunrise Package",
    description="Complimentary breakfast and early check-in for Ocean View bookings",
    synonyms=["morning special", "sunrise special"],
)
```

在这里，条件和动作都依赖于智能体理解这些术语的含义。

如果客户进来问道，

> **客户：** 我听说你们有一些能看大西洋景色的房间。那些是什么？

基于术语表词条，智能体就能理解条件 _"the user asks about Ocean View rooms"_ 被满足，随后它可以用动作 _"explain the Sunrise Package benefits"_ 来回应。

## 术语表 vs 指南 vs 智能体描述（Glossary vs Guidelines vs Agent Description）
每个组成部分在塑造你的智能体行为方面都发挥着独特的作用：

1. 术语表教会你的智能体"事物是什么"。例如，_"A Club Member is a guest who has stayed with us more than 5 times."_ 你可以拥有任意数量的术语。
1. 指南教会你的智能体"在各种情况下如何行事"。例如，_"When speaking with Club Members, acknowledge their loyalty status."_ 你可以拥有任意数量的指南。
1. 智能体描述（Agent Description）提供总体的上下文和个性。例如，_"You are a helpful hotel booking assistant for Boogie Nights."_ 智能体的描述是静态且有限的。

可以这样理解：术语表构建你的智能体的词汇表，指南塑造它的行为，而智能体描述设定它的总体上下文、角色、个性和语气。

## 术语表 vs 工具（Glossary vs Tools）
虽然术语表词条和工具都有助于你的智能体理解你的领域，但它们服务于根本不同的目的。术语表提供静态知识，而工具支持动态数据访问。

考虑一个酒店预订场景：

**术语表词条：**
> * **术语：** Club Member
> * **描述：** 一位已入住超过 5 次的客人
> * **同义词：** loyal guest, regular guest

**工具：**
`check_member_status(user_id)  # Returns current stay count and benefits`

术语表词条提供了关于 Club Member 是什么的一致定义，而工具可以检查数据库中某个特定用户的真实状态。类似地：

**术语表词条：**
> * **术语：** Ocean View Room
> * **描述：** 15-20 层面向大西洋的高级客房
> * **同义词：** seaside room, beach view

**工具：**
`check_room_availability(room_type, dates)  # Returns current availability and rates`

术语表帮助你的智能体理解 Ocean View Room 是什么，而工具提供关于特定房间可用性和定价的实时信息。

这种静态知识（术语表）与动态数据访问（工具）之间的分离，有助于创建清晰、可维护的智能体实现，既能处理一般性询问，也能处理具体的、以数据驱动的交互。