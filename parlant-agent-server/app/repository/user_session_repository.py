"""UserSessionRepository——用户会话台账（MySQL `user_sessions`）。

定位：Parlant 会话是引擎级事件源（事实源在 runtime）；本表是 **BFF 用户维度的
可查询台账/索引**——web 端"按用户查会话列表/详情"走这里，事件流详情仍回 runtime。

v2（2026-09-23）扩展——**会话生命周期 + 来源渠道**：
- `source`：会话来源渠道（online 线上正式问答 / simulate 模拟对话 / auto_sim 仿真对话）
- `ended_at` / `ended_reason`：主动关闭（normal）或超时自动失效（timeout）的时间与原因
- **有效性在台账侧判定**（不依赖 runtime sessions.json）：status=active 且未结束 且
  最近活跃在超时窗口内 → valid；否则 invalid + reason（ended / timeout）。

v3（2026-09-23）——**会话所属 Agent 状态/版本**（草稿试跑）：
- `agent_instance_id`：会话实际绑定的 runtime 实例 id（线上=`agent_id`；草稿试跑=`{agent_id}@draft`）
- `agent_version`：线上=发布版本号；草稿="draft"
- `agent_status`：published / draft
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import BigInteger, DateTime, JSON, String, delete, func, or_, and_, select, text, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.databases import MySqlConnection

# 会话来源渠道
SOURCE_ONLINE = "online"  # 线上客户正式问答渠道（可多部署渠道）
SOURCE_SIMULATE = "simulate"  # 模拟对话（web 工作台预览）
SOURCE_AUTO_SIM = "auto_sim"  # 自动仿真（阶段6）

# 结束原因
END_NORMAL = "normal"  # 客户/用户主动关闭
END_TIMEOUT = "timeout"  # 超过超时时间自动失效

# Agent 状态
AGENT_STATUS_PUBLISHED = "published"
AGENT_STATUS_DRAFT = "draft"


class Base(DeclarativeBase):
    pass


class UserSession(Base):
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
    source: Mapped[str] = mapped_column(String(32), default=SOURCE_ONLINE)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 会话发起时的变量生效初始快照 {变量名: {"value": 生效值, "source": "override"|"default"}}
    # （弹窗改了 → override 记修改后值；未改 → default 记 Agent 构建默认值）
    initial_variables: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # MySQL DATETIME 存 naive UTC


def _row_to_dict(row: UserSession, timeout_seconds: int = 86400) -> dict[str, Any]:
    d = {
        "id": row.id,
        "user_id": row.user_id,
        "session_id": row.session_id,
        "agent_id": row.agent_id,
        "agent_instance_id": row.agent_instance_id,
        "agent_version": row.agent_version,
        "agent_status": row.agent_status,
        "title": row.title,
        "status": row.status,
        "source": row.source,
        "ended_at": row.ended_at,
        "ended_reason": row.ended_reason,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "last_message_at": row.last_message_at,
        "initial_variables": row.initial_variables,
    }
    # 有效性判定（台账侧，不依赖 runtime）
    now = _utcnow()
    if row.status != "active" or row.ended_at is not None:
        d["valid"] = False
        d["invalid_reason"] = row.ended_reason or END_NORMAL
    else:
        last_active = row.last_message_at or row.created_at
        timed_out = (now - last_active) > timedelta(seconds=timeout_seconds)
        if timed_out:
            d["valid"] = False
            d["invalid_reason"] = END_TIMEOUT
        else:
            d["valid"] = True
            d["invalid_reason"] = None
    return d


class UserSessionRepository:
    def __init__(self, mysql: MySqlConnection, timeout_seconds: int = 86400) -> None:
        self._mysql = mysql
        self._timeout_seconds = timeout_seconds

    async def ensure_schema(self) -> None:
        async with self._mysql.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # 轻量迁移：老表补新列（source / ended_at / ended_reason / agent_*）
            # 注：agent_id 索引由 ORM index=True 经 create_all 创建，无需 ALTER。
            cols = {
                r[0]
                for r in (
                    await conn.execute(
                        text(
                            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user_sessions'"
                        )
                    )
                ).fetchall()
            }
            if "source" not in cols:
                await conn.execute(text("ALTER TABLE user_sessions ADD COLUMN source VARCHAR(32) NOT NULL DEFAULT 'online'"))
            if "ended_at" not in cols:
                await conn.execute(text("ALTER TABLE user_sessions ADD COLUMN ended_at DATETIME NULL"))
            if "ended_reason" not in cols:
                await conn.execute(text("ALTER TABLE user_sessions ADD COLUMN ended_reason VARCHAR(32) NULL"))
            if "agent_instance_id" not in cols:
                await conn.execute(text("ALTER TABLE user_sessions ADD COLUMN agent_instance_id VARCHAR(96) NULL"))
            if "agent_version" not in cols:
                await conn.execute(text("ALTER TABLE user_sessions ADD COLUMN agent_version VARCHAR(64) NULL"))
            if "agent_status" not in cols:
                await conn.execute(text("ALTER TABLE user_sessions ADD COLUMN agent_status VARCHAR(16) NULL"))
            if "initial_variables" not in cols:
                await conn.execute(text("ALTER TABLE user_sessions ADD COLUMN initial_variables JSON NULL"))

    # ------------------------------------------------------------ 写
    async def create(
        self,
        *,
        user_id: str,
        session_id: str,
        agent_id: str,
        title: str | None = None,
        source: str = SOURCE_ONLINE,
        agent_instance_id: str | None = None,
        agent_version: str | None = None,
        agent_status: str | None = None,
        initial_variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _utcnow()
        row = UserSession(
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            agent_instance_id=agent_instance_id or agent_id,
            agent_version=agent_version,
            agent_status=agent_status,
            title=title,
            status="active",
            source=source,
            initial_variables=initial_variables,
            created_at=now,
            updated_at=now,
        )
        async with self._mysql.session_factory() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return _row_to_dict(row, self._timeout_seconds)

    async def touch(
        self,
        session_id: str,
        *,
        status: str | None = None,
        title: str | None = None,
        last_message_at: datetime | None = None,
    ) -> None:
        values: dict[str, Any] = {"updated_at": _utcnow()}
        if status is not None:
            values["status"] = status
        if title is not None:
            values["title"] = title
        if last_message_at is not None:
            values["last_message_at"] = last_message_at.replace(tzinfo=None)
        async with self._mysql.session_factory() as session:
            await session.execute(
                update(UserSession).where(UserSession.session_id == session_id).values(**values)
            )
            await session.commit()

    async def close(self, session_id: str, reason: str = END_NORMAL) -> bool:
        """客户/用户主动关闭会话（正常结束）；超时失效由读取侧判定。"""
        now = _utcnow()
        async with self._mysql.session_factory() as session:
            r = await session.execute(
                update(UserSession)
                .where(UserSession.session_id == session_id)
                .values(status="ended", ended_at=now, ended_reason=reason, updated_at=now)
            )
            await session.commit()
        return r.rowcount > 0

    # ------------------------------------------------------------ 读
    async def list(
        self,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        source: str | None = None,
        session_id_like: str | None = None,
        status_filter: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """通用查询：按用户 / Agent / 来源渠道 / sessionId 模糊 / 有效性状态过滤；全部条件可空。

        `status_filter`：active=进行中（status=active 且未结束且未超时）；ended=已结束
        （正常结束或超时失效）——与 `_row_to_dict` 的有效性判定保持一致。
        """
        stmt = select(UserSession)
        if user_id:
            stmt = stmt.where(UserSession.user_id == user_id)
        if agent_id:
            stmt = stmt.where(UserSession.agent_id == agent_id)
        if source:
            stmt = stmt.where(UserSession.source == source)
        if session_id_like:
            stmt = stmt.where(UserSession.session_id.like(f"%{session_id_like}%"))
        if status_filter:
            cutoff = _utcnow() - timedelta(seconds=self._timeout_seconds)
            # 最近活跃 = COALESCE(last_message_at, created_at)
            last_active = func.coalesce(UserSession.last_message_at, UserSession.created_at)
            if status_filter == "active":
                stmt = stmt.where(
                    and_(
                        UserSession.status == "active",
                        UserSession.ended_at.is_(None),
                        last_active >= cutoff,
                    )
                )
            elif status_filter == "ended":
                stmt = stmt.where(
                    or_(
                        UserSession.status != "active",
                        UserSession.ended_at.isnot(None),
                        last_active < cutoff,
                    )
                )
        stmt = stmt.order_by(UserSession.updated_at.desc()).offset(offset).limit(limit)
        async with self._mysql.session_factory() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_row_to_dict(r, self._timeout_seconds) for r in rows]

    async def list_by_user(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return await self.list(user_id=user_id, limit=limit)

    async def get(self, session_id: str) -> dict[str, Any] | None:
        async with self._mysql.session_factory() as session:
            row = (
                await session.execute(
                    select(UserSession).where(UserSession.session_id == session_id)
                )
            ).scalar_one_or_none()
        return _row_to_dict(row, self._timeout_seconds) if row else None

    async def delete(self, session_id: str) -> bool:
        async with self._mysql.session_factory() as session:
            res = await session.execute(
                delete(UserSession).where(UserSession.session_id == session_id)
            )
            await session.commit()
        return res.rowcount > 0
