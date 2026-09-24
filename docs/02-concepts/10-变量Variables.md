> 来源：concepts/customization/variables.md，Parlant v3.3.1 官方英文文档中文翻译。

# 变量（Variables）

每位客户都是独特的，而在适当的情况下，你的智能体（Agent）可能会选择这样去对待他们。

变量（Variables）会丰富智能体（Agent）所看到的、关于其正在交谈的客户（Customer）的上下文。它们的目的是让你的智能体（Agent）感知到有助于其实现个性化服务的信息，就像一位体贴的客服代表了解并记住每位客户（Customer）的重要细节，从而让对方感到被倾听和理解一样。

当一位客户（Customer）与智能体（Agent）互动时，他们的变量会自动加载到其上下文中，使智能体能够根据客户的具体情况来定制其回复。

### 现实世界中的应用
让我们看看变量如何改变客户互动。想象你正在运营一个 SaaS 平台的支持智能体。你可能会跟踪诸如订阅计划、上次登录日期、每位客户使用了哪些功能，以及他们的公司规模等变量。

以两位就数据导出问题联系你的不同客户为例。Sarah 是一位使用免费（free）计划的初创公司创始人，她问道："我可以将我的数据导出到 Excel 吗？"你的智能体在了解她处于免费计划后，可以贴心地回复："虽然 Excel 导出是一项高级（premium）功能，但我可以向您展示如何使用我们的基础 CSV 导出功能。您是否也想了解一下我们高级计划中的高级报告功能？"

现在想象来自企业账户的 Tom 提出了同样的问题。智能体看到他的企业（enterprise）身份，但也注意到他的团队还没有探索过许多高级功能。它可能会回复："我可以帮您完成 Excel 导出！我注意到您的团队还没有尝试过我们的自动化报告套件——这是包含在您的企业计划中的，每周可以为您节省数小时时间。您想让我为您演示这两个功能吗？"


### 使用变量

单个变量标识一条特定的信息。例如，你可能会创建一个名为 `"subscription_plan"` 的变量。

然后，每位客户都可以在该变量下被分配一个唯一的值。例如，Tom 的该变量值可能是 `"enterprise"`。

设置变量值有两种方式。

1. 手动设置它们的值
2. 将它们关联到一个工具（Tool），该工具会根据动态数据自动获取值

#### 创建手动设置的变量

```python
variable = await agent.create_variable(
    name=NAME,
    description=DESCRIPTION,
)
```

#### 创建由工具驱动的变量
与某个工具（Tool）关联的变量会根据该工具的输出自动更新其值。这对于频繁变化、且智能体需要始终保持感知的动态数据非常有用。

假设你有如下工具（Tool）：
```python
@p.tool
async def get_variable_value(context: p.ToolContext) -> p.ToolResult:
  ...
```

然后你可以基于这个工具创建如下自动更新的变量：

```python
variable = await agent.create_variable(
    name=NAME,
    description=DESCRIPTION,
    tool=get_variable_value,
)
```

默认情况下，关联的工具会在智能体每次回复之前更新该变量的值。如果这种频繁重新加载数据没有必要，你可以通过指定其 _新鲜度规则（freshness rules）_ 来控制该值的刷新间隔（即控制关联工具被调用以生成新值的频率）。

```python
variable = await agent.create_variable(
    name=NAME,
    description=DESCRIPTION,
    tool=get_variable_value,
    freshness_rules=CRON_EXPRESSION,
)
```

新鲜度规则（freshness rules）遵循 [cron 表达式](https://en.wikipedia.org/wiki/Cron) 语法。如果你对 cron 还不熟悉，可以使用诸如 [crontab generator](https://crontab.cronhub.io/) 之类的工具来帮助你更轻松地定义周期语法。

> **手动值（Manual Values）**
>
> 即使是由工具驱动的变量，也可以在需要时手动设置它们的值。当你想要针对特定客户或客户群覆盖（override）工具的输出时，这一点非常有用。

#### 为客户设置变量值

```python
await variable.set_value_for_customer(
    customer=CUSTOMER,
    value=VALUE,
)
```

#### 为客户群设置变量值
你还可以通过指定[客户群](https://parlant.io/docs/concepts/entities/customers#customer-groups)的标签（tag）来为该群设置变量的值。

```python
await variable.set_value_for_tag(
    tag=TAG_ID,
    value=VALUE,
)
```


## 完整示例
下面展示我们如何实现一个订阅计划变量。

```python
@p.tool
async def get_subscription_plan(context: p.ToolContext) -> p.ToolResult:
    # Fetch the customer's subscription plan from your database
    return p.ToolResult(await get_plan_from_database(context.customer_id))
```

```python
variable = await agent.create_variable(
    name="subscription_plan",
    description="The customer's subscription plan",
    tool=get_subscription_plan,
)

await variable.set_value_for_customer(
    customer=p.Customer.guest(),
    value="Free Plan",  # Default value for non-registered customers
)
```


### 将上下文变量与指南结合使用

让我们探索指南（Guideline）和上下文变量如何协同工作，从而创造出真正智能的交互。想象你正在为一个数字银行运营一个 AI 支持智能体，其客户拥有不同的账户层级和交易模式。

下面是一条聚焦的指南（Guideline）：

```python
await agent.create_guideline(
    condition="the customer's account_tier is 'basic' "
      "AND they ask about instant international transfers",
    action="highlight our same-day domestic transfers that are free on their plan, "
      "then mention how the premium tier enables instant global payments with lower fees",
)
```

当处于基础（basic）层级的 Mark 询问如何给他出国留学的女儿汇款时，他听到的不再是一句生硬的"这只是高级会员专享"的回复，而是："我今天就可以帮您通过我们的标准国际转账来汇出这笔钱。顺便说一下，我们的高级账户可以即时完成这一操作，而且费用更低——您想了解更多吗？"