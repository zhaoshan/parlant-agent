"""对外 API 的请求/响应 DTO（定义读写、发布、会话…）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PublishBody(BaseModel):
    """发布请求体；version 缺省 -> 发布 draft/最新版本。"""

    version: str | None = None


class RollbackBody(BaseModel):
    """回滚请求体；version 必填。"""

    version: str


AnchorSide = Literal["top", "right", "bottom", "left"]


class EdgeAnchors(BaseModel):
    """单条连线的两端挂载点；缺省/None = 自动（由前端按几何关系决定）。"""

    from_anchor: AnchorSide | None = None
    to_anchor: AnchorSide | None = None


class NodePos(BaseModel):
    """节点在流程图画布中的左上角坐标（用户拖拽后的落点）。"""

    x: float
    y: float


class JourneyLayoutSave(BaseModel):
    """旅程流程图布局保存请求体（纯 UI，独立于定义层）。

    edges/nodes 均为**部分覆盖**：只存用户显式调整过的项，未存项回落自动布局；
    两者都随保存整体替换（前端每次提交全量有效集，孤儿键由前端 prune）。
    """

    edges: dict[str, EdgeAnchors] = Field(default_factory=dict)
    nodes: dict[str, NodePos] = Field(default_factory=dict)


class AgentSummary(BaseModel):
    agent_id: str
    published_version: str | None = None
    latest_version: str
    latest_status: str
    loaded: bool = False
    updated_at: Any = None


class SessionCreateBody(BaseModel):
    """创建会话请求体（阶段3.3 会话代理）。"""

    agent_id: str
    user_id: str | None = Field(default=None, description="当前用户（落 MySQL 台账用）")
    customer_id: str | None = None
    title: str | None = None
    source: str = Field(
        default="online",
        description="来源渠道：online(线上正式问答) / simulate(模拟对话) / auto_sim(自动仿真)",
    )
    mode: str = Field(
        default="published",
        description="试跑模式：published(线上已发布) / draft(当前草稿，独立 @draft 实例，不影响线上)",
    )
    variables: dict[str, Any] | None = Field(
        default=None,
        description="变量覆盖（按变量**名**，客户维度）：{name: value}，创建会话前写入 runtime "
        "（key=customer.id，覆盖 journey/Agent 构建默认值；同 customer 共享，仅本会话客户生效）",
    )


class CustomerCreateBody(BaseModel):
    """创建客户请求体（阶段3.3 代理 Parlant POST /customers）。"""

    name: str
    id: str | None = Field(default=None, description="客户 id（缺省由 runtime 生成）")
    metadata: dict[str, Any] | None = None
    tags: list[str] | None = None


__all__ = ["PublishBody", "RollbackBody", "AgentSummary", "SessionCreateBody", "CustomerCreateBody"]