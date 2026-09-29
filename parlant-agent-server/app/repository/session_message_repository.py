"""SessionMessageRepository——**消息级**对话历史（MySQL `session_messages`）。

定位：比 `user_sessions`（会话级台账）更细——**按真实消息记一条**：
用户提问一条、Agent 每次回复一条；流式输出时"首条插入、完成更新"，避免频繁写库。

表结构：
    id            BIGINT PK AUTO_INCREMENT
    session_id    VARCHAR(64)  索引（Parlant session id，uuid）
    request_id    VARCHAR(64)  索引（前端生成；同一次提问的用户消息 + Agent 多条回复共用）
    message_id    VARCHAR(64)  Parlant 事件 id（(session_id, message_id) 唯一 → 幂等 upsert）
    role          VARCHAR(16)  customer | agent
    user_id       VARCHAR(64)
    user_name     VARCHAR(128)
    agent_id      VARCHAR(64)
    agent_name    VARCHAR(128)
    content       MEDIUMTEXT   消息文本（多模态扩展：可存 JSON）
    content_type  VARCHAR(16)  default 'text'
    trace_id      VARCHAR(64)  可空（langfuse trace；用户提问通常无 → 留空不记）
    status        VARCHAR(16)  default 'completed'（streaming | completed）
    event_offset  INT           可空（Parlant 事件 offset，辅助排序）
    created_at    DATETIME
    updated_at    DATETIME
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.databases import MySqlConnection
from app.models.chat_session import Base, SessionMessage


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _row_to_dict(row: SessionMessage) -> dict[str, Any]:
    return {
        "id": row.id,
        "session_id": row.session_id,
        "request_id": row.request_id,
        "message_id": row.message_id,
        "role": row.role,
        "user_id": row.user_id,
        "user_name": row.user_name,
        "agent_id": row.agent_id,
        "agent_name": row.agent_name,
        "content": row.content,
        "content_type": row.content_type,
        "trace_id": row.trace_id,
        "status": row.status,
        "event_offset": row.event_offset,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


class SessionMessageRepository:
    def __init__(self, mysql: MySqlConnection) -> None:
        self._mysql = mysql

    async def ensure_schema(self) -> None:
        async with self._mysql.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # ------------------------------------------------------------ 写（幂等 upsert，按 session_id+message_id）
    async def upsert(
        self,
        *,
        session_id: str,
        request_id: str,
        message_id: str,
        role: str,
        content: str,
        user_id: str | None = None,
        user_name: str | None = None,
        agent_id: str | None = None,
        agent_name: str | None = None,
        trace_id: str | None = None,
        status: str = "completed",
        event_offset: int | None = None,
        content_type: str = "text",
    ) -> dict[str, Any]:
        """INSERT ... ON DUPLICATE KEY UPDATE：存在则更新内容/状态（流式完成更新），否则插入（首条）。"""
        from sqlalchemy.dialects.mysql import insert as mysql_insert

        now = _utcnow()
        stmt = mysql_insert(SessionMessage).values(
            session_id=session_id,
            request_id=request_id,
            message_id=message_id,
            role=role,
            user_id=user_id,
            user_name=user_name,
            agent_id=agent_id,
            agent_name=agent_name,
            content=content,
            content_type=content_type,
            trace_id=trace_id,
            status=status,
            event_offset=event_offset,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_duplicate_key_update(
            content=content,
            status=status,
            trace_id=trace_id,
            updated_at=now,
        )
        async with self._mysql.session_factory() as session:
            await session.execute(stmt)
            await session.commit()
        # 回读
        return await self.get(session_id, message_id)

    # ------------------------------------------------------------ 读
    async def get(self, session_id: str, message_id: str) -> dict[str, Any] | None:
        async with self._mysql.session_factory() as session:
            row = (
                await session.execute(
                    select(SessionMessage).where(
                        SessionMessage.session_id == session_id,
                        SessionMessage.message_id == message_id,
                    )
                )
            ).scalar_one_or_none()
        return _row_to_dict(row) if row else None

    async def list_by_session(
        self, session_id: str, request_id: str | None = None, limit: int = 500
    ) -> list[dict[str, Any]]:
        stmt = select(SessionMessage).where(SessionMessage.session_id == session_id)
        if request_id:
            stmt = stmt.where(SessionMessage.request_id == request_id)
        stmt = stmt.order_by(SessionMessage.id.asc()).limit(limit)
        async with self._mysql.session_factory() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_row_to_dict(r) for r in rows]

    async def list_by_request(self, request_id: str, limit: int = 500) -> list[dict[str, Any]]:
        stmt = (
            select(SessionMessage)
            .where(SessionMessage.request_id == request_id)
            .order_by(SessionMessage.id.asc())
            .limit(limit)
        )
        async with self._mysql.session_factory() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_row_to_dict(r) for r in rows]

    async def delete_by_session(self, session_id: str) -> bool:
        from sqlalchemy import delete

        async with self._mysql.session_factory() as session:
            res = await session.execute(
                delete(SessionMessage).where(SessionMessage.session_id == session_id)
            )
            await session.commit()
        return res.rowcount > 0
