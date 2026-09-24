"""会话代理服务（阶段3.3+）：转发 Parlant 会话 REST + SSE 透传 + MySQL 台账/消息历史写入。

定位（对照 plan 阶段3 任务 3.3/3.4/3.9 与 docs/03-production/08/09）：
- runtime（Parlant REST）是**会话/事件事实源**；本服务只是代理 + 用户维度索引。
- 创建会话：转发 `POST /sessions`，成功后往 MySQL `user_sessions` 落一行（3.4 闭环）。
- **消息级历史（session_messages，3.9 增强）**：用户提问记一条、Agent 每次回复记一条；
  流式输出"首条插入、完成更新"（幂等 upsert 按 session_id+message_id）；前端生成的
  request_id 供同一次提问的用户消息 + Agent 多条回复共用。
- 发消息/SSE：原样转发/透传；SSE 透传侧**旁路解析** ai_agent 消息事件落库（含 trace_id）。
- 按用户查会话列表：读 MySQL 台账（web /sessions 页 3.10）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from app.boundary import RuntimeClient
from app.repository import AgentDefinitionRepository, SessionMessageRepository, UserSessionRepository


class SessionService:
    def __init__(
        self,
        runtime: RuntimeClient,
        session_repo: UserSessionRepository,
        message_repo: SessionMessageRepository | None = None,
        agent_repo: AgentDefinitionRepository | None = None,
    ) -> None:
        self._runtime = runtime
        self._repo = session_repo
        self._msg_repo = message_repo
        self._agent_repo = agent_repo
        # session_id -> 前端生成的最新 request_id（SSE 侧给 Agent 回复共用）
        self._pending_requests: dict[str, str] = {}
        self._agent_names: dict[str, str] = {}  # agent_id -> name（惰性缓存）
        # 草稿试跑实例管理（@draft 独立实例）
        self._draft_loaded: dict[str, str] = {}  # {agent_id}@draft -> 已加载时的草稿定义指纹
        self._draft_sessions: dict[str, str] = {}  # draft 会话 session_id -> 归属 agent_id

    # ------------------------------------------------------------ 客户（代理）
    async def create_customer(
        self,
        name: str,
        customer_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        return await self._runtime.create_customer(name, customer_id, metadata, tags)

    async def list_customers(self) -> list[dict[str, Any]]:
        return await self._runtime.list_customers()

    # ------------------------------------------------------------ 会话（代理 + 台账）
    DRAFT_SUFFIX = "@draft"

    async def create_session(
        self,
        agent_id: str,
        customer_id: str,
        user_id: str | None = None,
        title: str | None = None,
        source: str = "online",
        mode: str = "published",
    ) -> dict[str, Any]:
        """转发 runtime 建会话；支持草稿试跑（mode=draft → 独立 @draft 实例，不影响线上）。

        会话实际绑定 agent_instance_id（线上=agent_id；草稿={agent_id}@draft），
        台账记录 agent_version/agent_status 以便校验"变更是否生效"。
        """
        if mode == "draft":
            # 1) 确保草稿实例已按最新 draft 定义加载（独立实例，线上实体不动）
            await self._ensure_draft_instance(agent_id)
            instance_id = f"{agent_id}{self.DRAFT_SUFFIX}"
            version, status = "draft", "draft"
        else:
            instance_id = agent_id
            version = await self._published_version(agent_id)
            status = "published"
        # 2) 绑定实例建会话
        session = await self._runtime.create_session(instance_id, customer_id, title)
        # 3) 落台账（记录实例/版本/状态）
        ledger = None
        try:
            ledger = await self._repo.create(
                user_id=user_id or customer_id,
                session_id=session["id"],
                agent_id=agent_id,
                agent_instance_id=instance_id,
                agent_version=version,
                agent_status=status,
                title=session.get("title") or title,
                source=source,
            )
            if mode == "draft":
                self._draft_sessions[session["id"]] = agent_id
        except Exception as exc:  # noqa: BLE001 - 台账失败不应阻断会话
            ledger = {"error": f"台账写入失败：{exc}"}
        return {"session": session, "ledger": ledger}

    async def _published_version(self, agent_id: str) -> str | None:
        try:
            doc = await self._agent_repo.get_published(agent_id)
            return doc.get("version") if doc else None
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------ 草稿实例管理
    async def _ensure_draft_instance(self, agent_id: str) -> None:
        """按**最新** draft 定义以 `{agent_id}@draft` 独立实例加载进 runtime。

        幂等 + **草稿变更感知**：每次新建草稿会话都比对当前草稿定义的内容指纹；
        若与已加载实例的指纹不同（Agent 构建里改过并保存），则重载最新草稿，
        确保新草稿会话用的运行时 Agent 是编辑后的最新版，而非编辑前的旧实例。
        局限：@draft 是共享实例（per agent），重载会影响仍在进行的旧草稿会话的后续消息。
        """
        instance_id = f"{agent_id}{self.DRAFT_SUFFIX}"
        # 取最新 draft 定义
        doc = None
        if self._agent_repo:
            versions = await self._agent_repo.list_versions(agent_id)
            for v in versions:
                if v.get("status") == "draft":
                    doc = await self._agent_repo.get(agent_id, v["version"])
                    break
        if not doc:
            raise ValueError(f"agent '{agent_id}' 没有草稿定义可试跑")
        definition = dict(doc["definition"])
        # 内容指纹（同一版本号被重复保存草稿时内容也会变，用定义 JSON 指纹而非版本号）
        import hashlib
        import json as _json

        fingerprint = hashlib.sha256(
            _json.dumps(definition, sort_keys=True, ensure_ascii=False, default=str).encode()
        ).hexdigest()
        # 复用缓存前先向 runtime 确认真实加载状态：runtime 重启会清空 @draft（transient 存储），
        # 若只靠本地指纹缓存判断，会误以为实例还在而跳过加载 → 绑定 @draft 建会话 404。
        loaded_in_runtime = False
        try:
            loaded_in_runtime = instance_id in {
                a.get("agent_id") for a in (await self._runtime.list_loaded()).get("agents", [])
            }
        except Exception:  # noqa: BLE001 - 查不到则按未加载处理（走 load，失败会显式抛）
            loaded_in_runtime = False
        if loaded_in_runtime and self._draft_loaded.get(instance_id) == fingerprint:
            return  # 实例确实在 runtime 且草稿未变，复用
        # 关键：后缀 id 作为独立实体加载（registry.load 按 definition.agent.id 建实体）
        suffixed = dict(definition)
        suffixed.setdefault("agent", {})["id"] = instance_id
        await self._runtime.load_agent(instance_id, suffixed)
        self._draft_loaded[instance_id] = fingerprint

    async def _release_draft_instance(self, agent_id: str) -> None:
        """无活跃草稿会话时立即卸载 @draft 实例。"""
        instance_id = f"{agent_id}{self.DRAFT_SUFFIX}"
        if instance_id not in self._draft_loaded:
            return
        remaining = sum(1 for a in self._draft_sessions.values() if a == agent_id)
        if remaining > 0:
            return
        try:
            await self._runtime.unload_agent(instance_id)
        except Exception as exc:  # noqa: BLE001
            print(f"[session-service] 卸载草稿实例失败 {instance_id}: {exc}")
        finally:
            self._draft_loaded.pop(instance_id, None)

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """会话详情：runtime 为准，附 MySQL 台账用户维度字段。"""
        session = await self._runtime.get_session(session_id)
        ledger = await self._repo.get(session_id)
        return {"session": session, "ledger": ledger}

    async def list_sessions(
        self,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        source: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        """会话列表（MySQL 台账，含有效性/来源渠道；条件可空）。"""
        rows = await self._repo.list(
            user_id=user_id, agent_id=agent_id, source=source, limit=limit, offset=offset
        )
        return {"sessions": rows, "count": len(rows)}

    async def close_session(self, session_id: str, reason: str = "normal") -> dict[str, Any]:
        """客户/用户主动关闭会话（台账侧标记结束）；若为草稿试跑会话，结束后释放 @draft 实例。"""
        ok = await self._repo.close(session_id, reason=reason)
        await self._after_session_ended(session_id)
        if not ok:
            return {"closed": False, "session_id": session_id}
        return {"closed": True, "session_id": session_id, "reason": reason}

    async def delete_session(self, session_id: str) -> dict[str, Any]:
        """删除会话台账 + 消息历史（前端列表删除）；若为草稿试跑会话，删除后释放 @draft 实例。"""
        deleted_ledger = await self._repo.delete(session_id)
        await self._after_session_ended(session_id)
        deleted_msgs = False
        if self._msg_repo:
            try:
                await self._msg_repo.delete_by_session(session_id)
                deleted_msgs = True
            except Exception as exc:  # noqa: BLE001
                self._note_ledger_error(session_id, exc)
        return {"deleted": deleted_ledger or deleted_msgs, "session_id": session_id}

    async def _after_session_ended(self, session_id: str) -> None:
        """会话关闭/删除后的清理：若为草稿试跑会话 → 无剩余活跃时立即卸载 @draft 实例。"""
        agent_id = self._draft_sessions.pop(session_id, None)
        if agent_id:
            try:
                await self._release_draft_instance(agent_id)
            except Exception as exc:  # noqa: BLE001
                self._note_ledger_error(session_id, exc)

    async def post_event(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """转发发消息/事件；若为 customer message 则 touch 台账并落消息记录。"""
        # 前端 request_id：写入事件 metadata（随事件留存 runtime），并登记 pending 供 SSE 关联 Agent 回复
        request_id = payload.get("metadata", {}).get("request_id") if isinstance(payload.get("metadata"), dict) else None
        event = await self._runtime.post_event(session_id, payload)
        if payload.get("kind") == "message" and payload.get("source") == "customer":
            self._pending_requests[session_id] = request_id or self._gen_request_id()
            try:
                await self._repo.touch(
                    session_id,
                    last_message_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            except Exception as exc:  # noqa: BLE001
                self._note_ledger_error(session_id, exc)
            if self._msg_repo:
                try:
                    await self.record_customer_message(session_id, payload, request_id or self._pending_requests[session_id], event)
                except Exception as exc:  # noqa: BLE001 - 消息记录失败不阻断转发
                    self._note_ledger_error(session_id, exc)
        return event

    async def list_by_user(self, user_id: str, limit: int = 100) -> dict[str, Any]:
        """按用户查会话列表（MySQL 台账；3.4/3.10）。"""
        rows = await self._repo.list_by_user(user_id, limit=limit)
        return {"user_id": user_id, "sessions": rows, "count": len(rows)}

    # ------------------------------------------------------------ 消息级历史（session_messages）
    async def record_customer_message(
        self,
        session_id: str,
        payload: dict[str, Any],
        request_id: str,
        event: dict[str, Any],
    ) -> dict[str, Any] | None:
        """用户提问记一条（role=customer）。用户提问通常无 langfuse trace_id → 留空。"""
        if not self._msg_repo:
            return None
        ledger = await self._repo.get(session_id)
        agent_id = (ledger or {}).get("agent_id")
        trace_id = event.get("trace_id")
        if trace_id in (None, "", "<main>"):
            trace_id = None
        return await self._msg_repo.upsert(
            session_id=session_id,
            request_id=request_id,
            message_id=event.get("id") or self._gen_request_id(),
            role="customer",
            content=str(payload.get("message", "")),
            user_id=(payload.get("metadata") or {}).get("user_id") if isinstance(payload.get("metadata"), dict) else None,
            user_name=(payload.get("metadata") or {}).get("user_name") if isinstance(payload.get("metadata"), dict) else None,
            agent_id=agent_id,
            agent_name=await self._agent_name(agent_id) if agent_id else None,
            trace_id=trace_id,
            status="completed",
            event_offset=event.get("offset"),
        )

    async def record_agent_message(self, session_id: str, event: dict[str, Any]) -> dict[str, Any] | None:
        """Agent 每次回复记一条（role=agent）；流式：首条插入、完成更新（幂等 upsert）。"""
        if not self._msg_repo:
            return None
        data = event.get("data") or {}
        participant = data.get("participant") or {}
        agent_id = participant.get("id") or data.get("agent_id")
        agent_name = participant.get("display_name")
        chunks = data.get("chunks")
        if isinstance(chunks, list):
            # 流式：chunks 列表，末尾 None 表示完成
            completed = bool(chunks) and chunks[-1] is None
            content = "".join(c for c in chunks if c is not None)
            status = "completed" if completed else "streaming"
        else:
            content = str(data.get("message", ""))
            status = "completed"
        trace_id = event.get("trace_id")
        if trace_id in (None, "", "<main>"):
            trace_id = None
        request_id = self._pending_requests.get(session_id) or self._gen_request_id()
        return await self._msg_repo.upsert(
            session_id=session_id,
            request_id=request_id,
            message_id=event.get("id") or self._gen_request_id(),
            role="agent",
            content=content,
            agent_id=agent_id,
            agent_name=agent_name or (await self._agent_name(str(agent_id)) if agent_id else None),
            trace_id=trace_id,
            status=status,
            event_offset=event.get("offset"),
        )

    async def get_messages(self, session_id: str, request_id: str | None = None) -> dict[str, Any]:
        """查消息历史（按会话，可选按 request_id 过滤）→ 模拟对话回看 / 观测。"""
        rows = (
            await self._msg_repo.list_by_session(session_id, request_id=request_id)
            if self._msg_repo
            else []
        )
        return {"session_id": session_id, "messages": rows, "count": len(rows)}

    # ------------------------------------------------------------ SSE 透传
    def stream_events(
        self,
        session_id: str,
        *,
        min_offset: int = 0,
        wait_for_data: int = 60,
        source: str | None = None,
        kinds: str | None = None,
    ) -> AsyncIterator[bytes]:
        """订阅 runtime SSE 并逐块产出（供 StreamingResponse 透传）。"""
        return self._runtime.stream_events(
            session_id,
            min_offset=min_offset,
            wait_for_data=wait_for_data,
            source=source,
            kinds=kinds,
        )

    # ------------------------------------------------------------ 内部
    async def _agent_name(self, agent_id: str) -> str | None:
        if agent_id in self._agent_names:
            return self._agent_names[agent_id]
        if not self._agent_repo:
            return None
        try:
            doc = await self._agent_repo.get_published(agent_id) or (
                await self._agent_repo.list_versions(agent_id)
                and await self._agent_repo.get(agent_id, (await self._agent_repo.list_versions(agent_id))[0]["version"])
            )
            name = (doc or {}).get("definition", {}).get("agent", {}).get("name")
        except Exception:  # noqa: BLE001
            name = None
        if name:
            self._agent_names[agent_id] = name
        return name

    @staticmethod
    def _gen_request_id() -> str:
        import uuid

        return str(uuid.uuid4())

    @staticmethod
    def _note_ledger_error(session_id: str, exc: Exception) -> None:
        print(f"[session-service] 记录失败 session={session_id}: {type(exc).__name__} {exc}")
