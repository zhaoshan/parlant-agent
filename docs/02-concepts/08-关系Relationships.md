> 来源：concepts/customization/relationships.md，Parlant v3.3.1 官方英文文档中文翻译。
>
> **⚠️ 官网更新注记（2026-09-30 核对，以 https://www.parlant.io/docs/concepts/customization/relationships 为准）**
> 本译文为本地 parlant 仓库 docs/ 的 v3.3.1 快照，官网已更新；经 parlant 源码溯源，
> 下述差异多数为「v3.3.1 代码已支持、仅文档过时」，已按官网回改正文：
> - 回改项：优先级（Priority）→ 排除（Exclusion），主方法 prioritize_over() → exclude()（prioritize_over 保留为别名，效果一致）/
>   蕴含（Entailment）解释改为时序问题（评估先于动作发生）
> - 官网新增、未全文重写项：Applying Relationships to Groups（server.create_tag/get_tag、标签作 source/target、
>   对标签依赖默认 AllOf、AnyOf/AllOf 修饰、depend_on_any OR 依赖）（完整见官网对应页）
> - 结构：官网「观察性指南」不再独立成节，融入 Exclusion/Dependency 各小节

# 关系（Relationships）

关系（relationships）定义了上下文元素彼此之间的关联方式。它们让你能够表达诸如此类的规则："这条指南只应在这条观察（observation）处于激活状态时触发"，或"当这两个旅程发生冲突时，这个胜出"。

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

管理指令不仅是一项技术挑战，也是一项人类建模（human modeling）挑战。我们必须考虑：对于一个预期会相当字面地理解这些指令的自动智能体，我们的指令彼此之间应该如何相关联。它们在不同上下文中应如何相互关联，尤其是在更微妙的情况下，最终只能由我们自己来决定。

在上面的案例中，我们希望确保当客户感到不安时，百事可乐指南被排除（excluded）。在 Parlant 中，这可以简单地表达如下：

```python
await handoff_if_upset.exclude(offer_pepsi_instead_of_coke)
```

## 关系的种类（Relationship Kinds）

虽然这些关系乍一听可能很复杂，但它们作为建模者给予你巨大的力量，使你能够更有能力持续地生成精确的回应。

我们建议简要回顾这些关系以了解它们的目的。

#### 关系类型（Relationship Types）
以下是受支持的关系。每种关系都位于一个 _source_（记为 **S**）和一个 _target_（记为 **T**）之间。

| 关系 | 效果 |
| --- | --- |
| [排除（Exclusion）](#排除exclusion) | 当 **S** 和 **T** 都被激活时，只应激活 **S** |
| [依赖（Dependency）](#依赖dependency) | 当 **S** 被激活时，除非 **T** 也被激活，否则将其停用 |
| [蕴含（Entailment）](#蕴含entailment) | 当 **S** 被激活时，**T** 应始终一并激活 |
| [消歧（Disambiguation）](#消歧disambiguation) | 当 **S** 被激活且两个或更多目标被激活时，询问客户以澄清 |

### 排除（Exclusion）
> 当 **S** 和 **T** 都被激活时，只应激活 **S**

```python
await source.exclude(target)
```

你也可以使用 `prioritize_over` 别名，它效果相同，但在你以"一条指南优先于另一条指南"的措辞思考时可能更直观。它们做的事情完全一样：

```python
await source.prioritize_over(target)
```

排除是最常见的关系。它解决两个问题：防止冲突的指令相互碰撞，以及控制对话中动作的先后顺序。

#### 观察排除指南（Observations Excluding Guidelines）
最常见的模式是：一条观察（observation）在触发时，将某些指南从智能体的上下文中剔除。这可以让不相关或矛盾的指令保持在外：

```python
customer_is_upset = await agent.create_observation(
    condition="The customer is becoming upset or frustrated"
)

upsell_premium = await agent.create_guideline(
    condition="The customer is browsing products",
    action="Suggest premium upgrades",
)

# 当客户感到不安时，不要尝试追加销售
await customer_is_upset.exclude(upsell_premium)
```

#### 指南排除指南（Guidelines Excluding Guidelines）
当两条指南可能冲突时，你可以声明哪一条优先：

```python
# 上面的披萨故事
await handoff_if_upset.exclude(offer_pepsi_instead_of_coke)
```

#### 关于控制先后顺序（On Controlling Precedence）
有时两条指南都是有效的，但不应同时触发。你可以控制顺序：

```python
complete_transaction = await agent.create_guideline(
    condition="The customer wants to make a transaction",
    action="Guide them through the process to its completion",
)

offer_savings = await agent.create_guideline(
    condition="The customer has less than $1,000 in their account",
    action="Offer savings plans",
)

# 不要用储蓄计划打断交易——一旦交易完成，储蓄指南就可以触发
await complete_transaction.exclude(offer_savings)
```

你可能会发现，例如当账户余额详情被引入会话中，而用户正处于提交交易的过程中时，上述指南会同时被激活。为了确保储蓄计划被提供——但要把握好时机，仅在交易完成之后——你可以让"完成交易"排除"提供储蓄计划"。一旦交易完成，与储蓄相关的指南就可以被激活了。

### 依赖（Dependency）
> 当 **S** 被激活时，除非 **T** 也被激活，否则将其停用

```python
await source.depend_on(target)
```

依赖确保一条指南或观察只在一个基线条件也成立时才会触发。这是观察（observation）门控指南（guidelines）的主要方式——让你能够将特定行为限定在正确的上下文中。

#### 观察门控指南（Observations Gating Guidelines）
最常见的模式：一条观察检测到一个宽泛的对话状态，而特定的指南只在该上下文内触发：

```python
customer_wants_deals = await agent.create_observation(
    condition="Customer expresses interest in special deals or discounts"
)

offer_seasonal_discount = await agent.create_guideline(
    condition="There is an active seasonal promotion",
    action="Mention the current seasonal discount",
)

offer_loyalty_reward = await agent.create_guideline(
    condition="The customer has been a member for over a year",
    action="Offer their loyalty reward",
)

# 这些指南只在客户真正对优惠感兴趣时触发
await offer_seasonal_discount.depend_on(customer_wants_deals)
await offer_loyalty_reward.depend_on(customer_wants_deals)
```

#### 将边缘场景限定到基线（Scoping Edge Cases to a Baseline）

当你构建流程时，可以通过让专门场景或边缘场景依赖于一个基线指南来处理它们。例如：

```python
handle_return = await agent.create_guideline(
    condition="The customer wants to return an order",
    action="Help them complete the return process",
)

no_order_number = await agent.create_guideline(
    condition="The customer isn't able to provide the order number",
    action="Load up their last order's items and ask them to confirm",
)

has_order_number = await agent.create_guideline(
    condition="The customer specified the exact order number",
    action="Load up that order's items and ask them to confirm",
)

# 这些只在退货流程中适用
await no_order_number.depend_on(handle_return)
await has_order_number.depend_on(handle_return)
```

通过让这些指南依赖于基线指南，你可以确保它们的评估始终在正确的上下文中进行。

### 蕴含（Entailment）
> 当 **S** 被激活时，**T** 应始终一并激活

```python
await source.entail(target)
```

蕴含解决的是一个时序问题。Parlant 会在合成回应*之前*评估所有的观察和指南。因此，如果指南 A 的动作将导致智能体去做指南 B 的条件所依赖的事情，那么 B 将不会匹配——因为在评估时，该动作尚未发生。

```python
explain_returns = await agent.create_guideline(
    condition="The customer asks about returns",
    action="Explain the return policy",
)

mention_warranty = await agent.create_guideline(
    condition="The agent is explaining the return policy",
    action="Also mention the 30-day warranty",
)

# 没有蕴含的话，mention_warranty 不会触发，因为在评估时
# 智能体还没有解释退货政策。
# 蕴含保证了只要 explain_returns 触发，mention_warranty 也会触发。
await explain_returns.entail(mention_warranty)
```

### 消歧（Disambiguation）
> 当 **S** 被激活且两个或更多目标 **T ∈ \{T₁, T₂, ...\}** 被激活时，询问客户以澄清他们想要采取哪个动作

```python
await source.disambiguate([target_1, target_2, ...])
```

当智能体无法判断几条指南中的哪一条适用时，消歧会强制它询问客户以澄清，而不是猜测：

```python
fetch_atm_limits = await agent.create_guideline(
    condition="The customer is inquiring about their ATM limits",
    action="Fetch the data from their account profile",
)

fetch_credit_card_limits = await agent.create_guideline(
    condition="The customer is inquiring about their credit card's limits",
    action="Fetch them from the card provider",
)

ambiguous_limits = await agent.create_observation(
    condition="The customer is inquiring about limits but it isn't clear which kind",
)

await ambiguous_limits.disambiguate([fetch_atm_limits, fetch_credit_card_limits])
```

如果客户说 *"What are my limits?"* 并且两条指南都匹配，智能体会询问他们指的是哪种限额，而不是任意挑选一个。

> **信息：观察（Info: Observations）**
>
> `Agent.create_observation()` 是创建一个不带动作的指南的简写形式。此指南仍会在上下文中被匹配，但它不携带任何要执行的动作。它对于在特定场景下（如上面的例子）创建指南之间的关系非常有用。

## 将关系应用于群组（Applying Relationships to Groups）

随着智能体的增长，管理单条指南与指南之间的关系会变得繁琐且容易出错。

[标签（Tags）](https://parlant.io/docs/concepts/customization/guidelines#tags)通过让你一次性针对一整组指南定义关系来解决这个问题。

```python
# 段落 A
compliance_guidelines = await server.create_tag("compliance-guidlines")

redirect_off_topic = await agent.create_guideline(..., tags=[compliance_guidelines])
block_financial_advice = await agent.create_guideline(..., tags=[compliance_guidelines])

# 段落 B（可以在不同的文件中）
discussing_flights = await agent.create_observation("...")
compliance_guidelines = await server.get_tag(name="compliance-guidlines")
await compliance_guidelines.prioritize_over(discussing_flights)
```

现在，每条带有 `compliance-guidlines` 标签的指南都优先于 `discussing_flights` 观察。当你添加一条新的合规指南时，只需给它打上标签即可——无需再编写新的关系连接。

### 标签作为目标（Tags as Targets）

标签也可以作为目标，让你针对一个群组定义关系：

```python
upsell_guidelines = await server.create_tag("upsell-guidelines")

offer_seat_upgrade = await agent.create_guideline(..., tags=[upsell_guidelines])
offer_lounge_access = await agent.create_guideline(..., tags=[upsell_guidelines])

# 当客户感到不安时，一次性排除所有追加销售指南
customer_is_upset = await agent.create_observation("...")
await customer_is_upset.exclude(upsell_guidelines)
```

#### 对标签的依赖（Dependency on a Tag）

默认情况下，当一条指南依赖一个标签时，该依赖要求标签的**所有**成员都处于激活状态。这就是 `AllOf` 语义——每个打上标签的成员都必须匹配，依赖才得到满足：

```python
returns_tag = await server.create_tag("returns")

handle_online_return = await agent.create_guideline(
    condition="The customer wants to return an online order",
    action="Guide them through the online return process",
    tags=[returns_tag],
)

handle_store_return = await agent.create_guideline(
    condition="The customer wants to return an in-store purchase",
    action="Guide them through the in-store return process",
    tags=[returns_tag],
)

offer_exchange = await agent.create_guideline(
    condition="The customer might prefer an exchange over a refund",
    action="Suggest exchanging the item instead",
)

# offer_exchange 只会在所有退货指南都激活时触发
await offer_exchange.depend_on(returns_tag)
```

#### `AnyOf` 与 `AllOf` 修饰符（AnyOf and AllOf Modifiers）

你可以使用 `AnyOf` 和 `AllOf` 包装器显式控制标签目标如何被评估：

* **`AnyOf(tag)`**——依赖/关系在标签的**至少一个**成员激活时得到满足。
* **`AllOf(tag)`**——依赖/关系仅在标签的**所有**成员都激活时才得到满足。这是当你传入一个裸 `Tag` 时的默认行为。

```python
from parlant.sdk import AnyOf, AllOf

# offer_exchange 在任意一条退货指南激活时触发——
# 客户不需要同时进行两种退货
await offer_exchange.depend_on(AnyOf(returns_tag))

# 等价于传入裸标签（所有成员都必须激活）
await offer_exchange.depend_on(AllOf(returns_tag))
```

#### `depend_on_any`——OR 依赖（OR Dependencies）

当你需要一条指南在**至少一个**目标（无论是标签、指南还是旅程）激活时触发，请使用 `depend_on_any`：

```python
login_detected = await agent.create_observation(
    condition="The customer just logged in",
)

returning_customer = await agent.create_observation(
    condition="The customer has interacted with us before",
)

personalized_greeting = await agent.create_guideline(
    condition="The conversation is starting",
    action="Greet the customer by name",
)

# 只要两个观察中的任意一个激活，问候就触发
await personalized_greeting.depend_on_any(login_detected, returning_customer)
```

`depend_on_any` 将其目标组合在一起，使依赖在任意一个目标匹配时即得到满足。与之对比，`depend_on` 要求**所有**目标都处于激活状态。

> **提示（Tip）：**
>
> `AnyOf`/`AllOf` 控制的是**单个标签目标**如何被评估（标签*成员*的 any vs. all）。`depend_on_any` 控制的是**多个目标**彼此之间的关系（依赖中*目标*的 any vs. all）。
>
> 你可以将它们组合使用：

```python
# 在以下任一情况满足时触发：returns_tag 的任意成员激活，或 login_detected 激活
await some_guideline.depend_on_any(AnyOf(returns_tag), login_detected)
```
