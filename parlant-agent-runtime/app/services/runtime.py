"""运行期单例：把 p.Server、AgentRegistry 绑在一起。

configure_api 在 p.Server 装配期被调用，彼时 registry 已随 __aenter__ 创建。
internal API 通过 get_runtime() 延迟取用，避免在 Server 构造前传递未就绪对象。

阶段3.2：定义层已归 parlant-agent-server 独占写（AgentDefinitionRepository），
runtime 不再持有定义存储；定义经 server 推送（/internal/agents/{id}/load）或启动拉取。
"""

from __future__ import annotations

from dataclasses import dataclass

import parlant.sdk as p

from app.services.agent_registry import AgentRegistry


@dataclass
class Runtime:
    server: p.Server
    registry: AgentRegistry


_RT: Runtime | None = None


async def init_runtime(server: p.Server) -> Runtime:
    global _RT
    _RT = Runtime(
        server=server,
        registry=AgentRegistry(server),
    )
    return _RT


def get_runtime() -> Runtime:
    if _RT is None:
        raise RuntimeError("Runtime 未初始化：init_runtime() 须在 p.Server __aenter__ 之后调用")
    return _RT
