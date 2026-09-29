"""chat/session 域 ORM 实体（MySQL 台账表结构，会话+消息两级）。

两个 repo（user_session_repository / session_message_repository）**共享同一个
``Base(DeclarativeBase)``**——两张表进同一 metadata，`create_all` 统一建表、
跨表查询/迁移不踩"各 repo 各持 Base"的坑。实体只在 models 定义，访问逻辑
留在 repository（表结构与数据访问分离）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserSession(Base):
    """用户会话台账（`user_sessions`）：会话级生命周期记录，供按用户查会话详情。"""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_instance_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active")
    source: Mapped[str] = mapped_column(String(32), default="online")
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 会话发起时的变量生效初始快照 {变量名: {"value": 生效值, "source": "override"|"default"}}
    # （弹窗改了 → override 记修改后值；未改 → default 记 Agent 构建默认值）
    initial_variables: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class SessionMessage(Base):
    """消息级对话历史（`session_messages`）：比 user_sessions 更细，按真实消息记一条。"""

    __tablename__ = "session_messages"
    __table_args__ = (
        Index("uq_session_message", "session_id", "message_id", unique=True),
        Index("ix_msg_request", "request_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(64))
    message_id: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(16))
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(16), default="text")
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="completed")
    event_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
