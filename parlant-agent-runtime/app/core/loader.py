"""AgentLoader 门面：编排 幂等预删 → 装配（builder）→ 评估调度（evaluator）。

公开 API 与拆分前一致（load/unload），AgentRegistry 等调用方零感知。装配细节见
builder.py，评估编排见 evaluator.py，级联删除见 unloader.py，小工具见 helpers.py。

幂等语义：load() 先检查 agent_id 是否已存在——存在则先卸载（删 agent 及其
打 agent 标签的全部子实体）再重建，保证「重复加载同版本不重复建实体」、
「发布即生效」。装配失败回滚删干净，避免"建了一半"的 agent。
"""

from __future__ import annotations

import parlant.sdk as p

from app.models.definition import AgentDefinition
from app.core.builder import AgentBuilder
from app.core.evaluator import AgentEvaluator
from app.core.unloader import AgentUnloader


class AgentLoader:
    """定义 -> Parlant 实体装配门面（每个 p.Server() 一个实例即可）。"""

    def __init__(self, server: p.Server) -> None:
        self._server = server
        self._builder = AgentBuilder(server)
        self._evaluator = AgentEvaluator(server)
        self._unloader = AgentUnloader(server)

    async def load(self, definition: AgentDefinition) -> p.Agent:
        agent_def = definition.agent
        # 幂等：已存在则先卸载（含子实体）再重建
        if await self._server.find_agent(id=agent_def.id):
            await self._unloader.delete_entities(agent_def.id)
        try:
            agent, journey_map = await self._builder.build(definition)
        except Exception:
            # 失败回滚：删干净（仅当 agent 已存在时；create_agent 未成功则无可删）
            if await self._server.find_agent(id=agent_def.id):
                await self._unloader.delete_entities(agent_def.id)
            raise
        # 装配成功后调度后台评估（旅程分叉表 + 指南元数据；见 evaluator）
        self._evaluator.evaluate_journeys_now(agent_def.id, list(journey_map.values()))
        self._evaluator.evaluate_guidelines_now()
        return agent

    async def unload(self, agent_id: str) -> bool:
        return await self._unloader.unload(agent_id)
