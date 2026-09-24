"""阶段2.4：AgentRegistry——多 Agent 动态调度。

维护 agent_id -> 已加载 Parlant Agent 的映射，支持：
- 运行时加载：loader 转换后注册进 p.Server()，无需重启；
- 热更新：load 同 agent_id 先卸载旧实体再重建（见 AgentLoader.load 幂等语义）；
- 回滚：Registry 记住每个 agent 当前生效的定义版本，配合 DefinitionStore 取历史版本重载。

全局资源（内置工具/检索器/向量库连接）在模块级注册一次（app.services.builtin_tools），
各 agent 引用，不随 agent 增删重建。
"""

from __future__ import annotations

import parlant.sdk as p

from app.models import AgentDefinition
from app.services.agent_loader import AgentLoader


class AgentRegistry:
    def __init__(self, server: p.Server) -> None:
        self._server = server
        self._loader = AgentLoader(server)
        self._agents: dict[str, p.Agent] = {}
        self._definitions: dict[str, AgentDefinition] = {}

    async def load(self, definition: AgentDefinition) -> p.Agent:
        """装配（或热更新）一个 agent 并注册。"""
        agent = await self._loader.load(definition)
        self._agents[definition.agent.id] = agent
        self._definitions[definition.agent.id] = definition
        return agent

    async def unload(self, agent_id: str) -> bool:
        """停用并卸载一个 agent。"""
        ok = await self._loader.unload(agent_id)
        self._agents.pop(agent_id, None)
        self._definitions.pop(agent_id, None)
        return ok

    def get(self, agent_id: str) -> p.Agent | None:
        return self._agents.get(agent_id)

    def list(self) -> list[str]:
        return list(self._agents)

    def definition(self, agent_id: str) -> AgentDefinition | None:
        """当前生效的定义（回滚/对账用）。"""
        return self._definitions.get(agent_id)

    async def reload(self, definition: AgentDefinition) -> p.Agent:
        """显式热更新（等价 load，语义化命名供 publish/rollback 调用）。"""
        return await self.load(definition)
