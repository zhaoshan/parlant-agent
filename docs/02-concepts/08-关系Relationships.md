> 来源：concepts/customization/relationships.md，Parlant v3.3.1 官方英文文档中文翻译。

# 关系（Relationships）

定义**指南（guidelines）**和**旅程（journeys）**彼此之间的关联方式，是行为建模中一个强大（且进阶）的部分。

#### 背景与动机（Background & Motivation）

从前，我们的团队在构建一个披萨销售智能体，它拥有以下指南（以及其他指南）：
```python
offer_pepsi_instead_of_coke = await agent.create_guideline(
    condition="The customer wants a coke",
    action="Tell them we only have Pepsi",
)

handoff_if_upset = await agent.create_guideline(
    condition="The customer is becoming upset",
    action="Apologize and tell them you will transfer them to a manager",
    tools=[handoff_to_human_manager],
)
```

一开始这运行得很好，直到我们遇到了以下场景：

> **智能体：** 您点的餐需要来点喝的吗？
>
> **用户：** 请来一杯可乐
>
> **智能体：** 抱歉，我们只有百事可乐。您要不要换成这个？
>
> **用户：** 等等，什么？我讨厌百事可乐。你们到底为什么没有可乐？
>
> **智能体：** 对此给您带来不便，我很抱歉。让我把您转接给经理。同时，我可以给您来一罐百事可乐吗？
>
> **用户：** 你是在拿我寻开心吗？

智能体的回应绝对不是我们想要的，因为它可能会给人一种带有讽刺意味的敌意。但这个可怜的 AI 智能体只是在遵循我们给它的指南，依据的是我们所设定的指南条件。

而事情的关键在于：你会发现，管理指令不仅是一项技术挑战，也是一项人类建模（human modeling）挑战。我们必须考虑：对于一个预期会相当字面地理解这些指令的自动智能体，我们的指令彼此之间应该如何相关联。它们在不同上下文中应如何相互关联，尤其是在更微妙的情况下，最终只能由我们自己来决定。

在上面的例子中，我们希望确保第二条指南的优先级*高于*第一条指南。我们需要一种优先级关系（priority relationship），如今在 Parlant 中，这一关系可以非常简单地表达如下：

```python
await handoff_if_upset.prioritize_over(offer_pepsi_instead_of_coke)
```

## 关系的种类（Relationship Kinds）

虽然这些关系乍一听可能很复杂，但它们作为建模者给予你巨大的力量，使你能够更有能力持续地生成精确的回应。

我们建议简要回顾这些关系以了解它们的目的。

#### 关系类型（Relationship Types）
以下是受支持的关系。每种关系都位于一个 _source_（记为 **S**）和一个 _target_（记为 **T**）之间。

点击某个关系类型以了解更多信息。

- [蕴含（Entailment）](https://parlant.io/docs/guidelines/relationships#entailment)：当 **S** 被激活时，**T** 应始终被激活
- [优先级（Priority）](https://parlant.io/docs/guidelines/relationships#priority)：当 **S** 和 **T** 都被激活时，只应激活 **S**
- [依赖（Dependency）](https://parlant.io/docs/guidelines/relationships#dependency)：当 **S** 被激活时，除非 **T** 也被激活，否则将其停用
- [消歧（Disambiguation）](https://parlant.io/docs/guidelines/relationships#disambiguation)：当 **S** 被激活且两个或更多目标 **T ∈ \{T₁, T₂, ...\}** 被激活时，询问客户以澄清他们想要采取哪个动作

### 蕴含（Entailment）
> 当 **S** 被激活时，**T** 应始终被激活

```python
await source.entail(target)
```

要理解蕴含的必要性，我们首先需要理解，当智能体即将对客户说些什么时，Parlant 是如何选择激活哪些指南的。

基本上，Parlant 会检查会话（session）在当前时刻的状态，并就此提出问题："这条指南现在相关吗？""那条指南现在相关吗？"。

为此，它主要测试各条指南的 _条件（conditions）_。

这本身看似能很好地工作，直到你考虑如下形式的两个指南：

> * **指南 A：** 当 X 时，则 Y
> * **指南 B：** 当 Y 时，则 Z

现在设想这样一种情形：查看一个会话，我们确定 _X_ 确实适用，但 _Y_ 并不适用。按照上面那种朴素的逻辑，我们只会向智能体输入那条"做 Y"的指南。

但是，当我们退一步分析这个案例时，我们知道智能体马上就要去做 _Y_，这意味着，根据我们已安装的指南，_Z_ 也应适用。

这就是蕴含所实现的功能：要求每当 _A_ 被激活时，_B_ 也被激活。



### 优先级（Priority）
> 当 **S** 和 **T** 都被激活时，只应激活 **S**

```python
await source.prioritize_over(target)
```

优先级可以用于多种使用场景。最常见的两种是：
1. 创建互斥的指南
1. 控制对话中动作的流程和先后顺序

#### 关于控制先后顺序（On Controlling Precedence）
你可能有两条恰好同时被激活的指南，例如：
> * 当客户想要进行交易时，则引导他们完成该流程直至结束
> * 当客户账户中的余额少于 1,000 美元时，则为其提供储蓄计划

你可能会发现，例如当账户余额详情被引入会话中，而用户正处于提交交易的过程中时，上述指南会同时被激活。

为了确保储蓄计划被提供——但要把握好时机，仅在交易完成之后——你可以将"完成交易"的优先级设为高于"提供储蓄计划"。一旦交易完成，与储蓄相关的指南就可以被激活了。

### 依赖（Dependency）
> 当 **S** 被激活时，除非 **T** 也被激活，否则将其停用

```python
await source.depend_on(target)
```

依赖帮助你确保，只有当其他基线条件（baseline conditions）也成立时，某条指南才会被激活。

最常见的用例是确保更具体的条件只在适当的基线上下文中被激活。

#### 将具体条件情境化（Contextualizing Specific Conditions）

当你构建流程时，可以通过让专门场景或边缘场景依赖于流程的基线指南来处理它们。例如：

##### 基线指南（Baseline Guideline）
> 当客户想要退回订单时，则帮助他们完成退货流程

##### 依赖指南（Dependent Guidelines）
> * 当客户无法提供订单号时，则加载他们最近一笔订单的商品，并请他们确认那是否是他们的订单
> * 当客户明确给出确切的订单号时，则加载该订单的商品，并请他们确认那是否是他们的订单

通过让这些指南依赖于基线指南，你可以确保它们的评估始终在正确的上下文中进行。

### 消歧（Disambiguation）
> 当 **S** 被激活且两个或更多目标 **T ∈ \{T₁, T₂, ...\}** 被激活时，询问客户以澄清他们想要采取哪个动作

```python
await source.disambiguate([target_1, target_2, ...])
```

你可能会遇到这样的情况：在两条（或更多）相互竞争的指南之间，由于歧义，其中部分或全部在同一时间被激活，从而导致指令遵循上的混乱。

例如，如果客户向银行智能体发送了消息 _"What are my limits?"_，而你拥有以下指南，每条指南都根据引擎的解读被乐观地激活了：

> * 当客户在询问他们的 ATM 限额时，则从他们的账户资料中获取数据
> * 当客户在询问他们信用卡的限额时，则从发卡机构获取这些数据

为了澄清客户的意图，你可以添加一条[观察性指南（observational guideline）](https://parlant.io/docs/guidelines/relationships#observational-guidelines)来在这两个动作之间进行消歧：

```python
ambiguous_limits = await agent.create_observation(
    condition="The customer is inquiring about limits but it isn't clear which kind",
)

await ambiguous_limits.disambiguate([fetch_atm_limits, fetch_credit_card_limits])
```

> **信息：观察（Info: Observations）**
>
> `Agent.create_observation()` 是创建一个不带动作的指南的简写形式。此指南仍会在上下文中被匹配，但它不携带任何要执行的动作。它对于在特定场景下（如上面的例子）创建指南之间的关系非常有用。

## 观察性指南（Observational Guidelines）
当使用关系建模对话的边缘场景时，你可能会发现自己希望添加一条指南，仅仅是为了（利用其条件）确定特定情况适用，并且——仅在这些情况下——使用关系来激活或停用其他指南或旅程。

为此，Parlant 支持一种特殊类型的指南，称为**观察性指南（observational guideline）**。这是一种没有动作的指南，通常仅用于确定某些条件是否适用，并围绕这些条件创建关系。

```python
observation = await agent.create_observation(condition=CONDITION)
```

然后，你可以用一些有趣的方式来使用这个观察，例如：

1. 通过将观察的优先级设为高于其他指南来停用它们。
```python
await observation.prioritize_over(other_guideline)
```

2. 将其他指南的作用域限定为仅在观察处于激活状态时适用。
```python
await other_guideline.depend_on(observation)
```

以及其他创造性的用法！