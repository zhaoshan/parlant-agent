"""阶段0.6：官方 quickstart 医疗保健示例（healthcare.py 复刻 + langfuse 追踪）。

一键跑通：
    python examples/healthcare_demo.py

- 用 litellm + langfuse（读 .env，OTEL_* 自动派生）启动 p.Server
- 创建 Healthcare Agent + 领域术语 + 预约旅程（含工具）+ 全局/旅程指南
- 退出 async with 块时 __aexit__ 真正启动 HTTP 服务（sdk.py:4340）并阻塞

交互方式（等价于官方示例里「浏览器打开 localhost:8800」）：
    - 聊天 UI：   http://localhost:8800/chat
    - REST API：  POST /sessions 创建会话，POST /sessions/{id}/events 发消息

来源：docs/01-quickstart/02-快速入门示例.md（官方 examples/healthcare.py）
"""

import asyncio
from datetime import datetime

import parlant.sdk as p

from app.boundary.policies import build_container
from app.config import get_settings
from app.routers.api_extensions import configure_api
from app.utils.observability import configure_langfuse_otel

DEMO_HOST = "127.0.0.1"
DEMO_PORT = 8800  # p.Server 官方默认端口


# ---------------------------------------------------------------- 工具
@p.tool
async def get_upcoming_slots(context: p.ToolContext) -> p.ToolResult:
    """Simulate fetching available appointment times from a database or API."""
    return p.ToolResult(data=["Monday 10 AM", "Tuesday 2 PM", "Wednesday 1 PM"])


@p.tool
async def get_later_slots(context: p.ToolContext) -> p.ToolResult:
    """Simulate fetching later available times."""
    return p.ToolResult(data=["November 3, 11:30 AM", "November 12, 3 PM"])


@p.tool
async def schedule_appointment(context: p.ToolContext, datetime: datetime) -> p.ToolResult:
    """Simulate scheduling the appointment."""
    return p.ToolResult(data=f"Appointment scheduled for {datetime}")


# ---------------------------------------------------------------- 领域术语
async def add_domain_glossary(agent: p.Agent) -> None:
    await agent.create_term(
        name="Office Phone Number",
        description="The phone number of our office, at +1-234-567-8900",
    )
    await agent.create_term(
        name="Office Hours",
        description="Office hours are Monday to Friday, 9 AM to 5 PM",
    )
    await agent.create_term(
        name="Charles Xavier",
        synonyms=["Professor X"],
        description="The renowned doctor who specializes in neurology",
    )


# ---------------------------------------------------------------- 预约旅程
async def create_scheduling_journey(agent: p.Agent) -> p.Journey:
    journey = await agent.create_journey(
        title="Schedule an Appointment",
        description="Helps the patient find a time for their appointment.",
        triggers=["The patient wants to schedule an appointment"],
    )

    t0 = await journey.initial_state.transition_to(
        chat_state="Determine the reason for the visit"
    )
    t1 = await t0.target.transition_to(tool_state=get_upcoming_slots)
    t2 = await t1.target.transition_to(
        chat_state="List available times and ask which one works for them"
    )

    # 开心路径：患者选了一个时间
    t3 = await t2.target.transition_to(
        chat_state="Confirm the details with the patient before scheduling",
        condition="The patient picks a time",
    )
    t4 = await t3.target.transition_to(
        tool_state=schedule_appointment,
        condition="The patient confirms the details",
    )
    t5 = await t4.target.transition_to(
        chat_state="Confirm the appointment has been scheduled"
    )
    await t5.target.transition_to(state=p.END_JOURNEY)

    # 否则：都不可行，问更晚的时间
    t6 = await t2.target.transition_to(
        tool_state=get_later_slots,
        condition="None of those times work for the patient",
    )
    t7 = await t6.target.transition_to(
        chat_state="List later times and ask if any of them works"
    )
    # 选定了时间则回到开心路径
    await t7.target.transition_to(state=t3.target, condition="The patient picks a time")
    # 仍不可行则让患者致电办公室
    t8 = await t7.target.transition_to(
        chat_state="Ask the patient to call the office to schedule an appointment",
        condition="None of those times work for the patient either",
    )
    await t8.target.transition_to(state=p.END_JOURNEY)

    # 旅程级指南（边缘情况）
    await journey.create_guideline(
        condition="The patient says their visit is urgent",
        action="Tell them to call the office immediately",
    )

    return journey


# ---------------------------------------------------------------- 全局指南
async def create_global_guidelines(agent: p.Agent) -> None:
    await agent.create_guideline(
        condition="The patient asks to talk to a human agent",
        action="Ask them to call the office, providing the phone number",
    )
    await agent.create_guideline(
        condition="The patient inquires about something that has nothing to do with "
        "our healthcare",
        action="Kindly tell them you cannot assist with off-topic inquiries - do not "
        "engage with their request.",
    )


# ---------------------------------------------------------------- 主流程
async def main() -> None:
    settings = get_settings()
    configure_langfuse_otel(settings)

    async with p.Server(
        host=DEMO_HOST,
        port=DEMO_PORT,
        nlp_service=p.NLPServices.litellm,  # OpenAI 兼容端点 + 自定义模型名
        configure_api=configure_api,         # /health + OTel FastAPI instrument（trace 根 span）
        configure_container=build_container, # DevelopmentAuthorizationPolicy（放行 REST）
    ) as server:
        agent = await server.create_agent(
            name="Healthcare Agent",
            description="Is empathetic and calming to the patient.",
        )
        await add_domain_glossary(agent)
        await create_scheduling_journey(agent)
        await create_global_guidelines(agent)

        print(f"✅ Healthcare Agent 已创建：{agent.id}")
        print(f"   聊天 UI：   http://{DEMO_HOST}:{DEMO_PORT}/chat")
        print(f"   就绪后（__aexit__ 启动服务）即可交互，Ctrl+C 退出。")

    # 退出 async with 时 __aexit__ 启动 HTTP 服务并阻塞在此。


if __name__ == "__main__":
    asyncio.run(main())