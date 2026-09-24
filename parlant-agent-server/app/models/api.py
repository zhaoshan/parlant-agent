"""对外 API 的请求/响应 DTO（定义读写、发布、会话…）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PublishBody(BaseModel):
    """发布请求体；version 缺省 -> 发布 draft/最新版本。"""

    version: str | None = None


class RollbackBody(BaseModel):
    """回滚请求体；version 必填。"""

    version: str


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


class CustomerCreateBody(BaseModel):
    """创建客户请求体（阶段3.3 代理 Parlant POST /customers）。"""

    name: str
    id: str | None = Field(default=None, description="客户 id（缺省由 runtime 生成）")
    metadata: dict[str, Any] | None = None
    tags: list[str] | None = None


__all__ = ["PublishBody", "RollbackBody", "AgentSummary", "SessionCreateBody", "CustomerCreateBody"]