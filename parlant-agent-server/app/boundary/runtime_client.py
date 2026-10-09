"""RuntimeClient——parlant-agent-runtime（Parlant 引擎）的 HTTP 客户端（httpx 异步）。

职责（对应 plan/阶段3 任务 3.1-3.3 的 boundary 层）：
- Agent 加载编排：`load_agent` / `unload_agent` / `list_loaded`（调 runtime `/internal/*`）。
- 健康探活：`health`（供本服务 /health 聚合展示）。
- 会话代理 + SSE 透传（3.3）：`create_session` / `get_session` / `list_sessions` /
  `create_customer` / `list_customers` / `post_event`（转发 Parlant REST），
  `stream_events`（以 httpx 流式订阅 runtime `GET /sessions/{id}/events?sse=true`，
  供 `routers/sessions.py` 用 StreamingResponse 逐帧转发给 web）。

目标契约（plan 阶段2 任务 2.5 定的 runtime `/internal/*` + Parlant REST）：
    POST /internal/agents/{id}/load     # 接收完整定义 JSON，热加载（幂等）
    POST /internal/agents/{id}/unload   # 卸载引擎实体
    GET  /internal/agents               # 已加载列表
    GET  /health                        # 引擎健康
    POST /sessions?allow_greeting=false # 建会话 {customer_id, agent_id, title}
    POST /customers                     # 建客户 {name, id?, metadata?, tags?}
    POST /sessions/{id}/events          # 发事件 {kind, source, message}
    GET  /sessions/{id}/events?sse=true # SSE 事件流（EventSource 兼容 data: 帧）
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx


class RuntimeClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        *,
        internal_token: str = "",
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._token = internal_token

    def _client(self, timeout: float | None = None) -> httpx.AsyncClient:
        """构造 httpx 客户端：trust_env=False 直连（服务间 127.0.0.1 不可被系统代理劫持），
        统一带 `X-Internal-Token`（doc09 §4.4 runtime 内部鉴权；未配置则不带头——runtime
        若启用了内部鉴权会以 401 拒绝，立即暴露两边 .env 的 INTERNAL_TOKEN 不一致）。"""
        headers: dict[str, str] = {}
        if self._token:
            headers["X-Internal-Token"] = self._token
        return httpx.AsyncClient(
            trust_env=False,
            timeout=timeout if timeout is not None else self._timeout,
            headers=headers,
        )

    # ------------------------------------------------------------ 健康 / 加载编排
    async def health(self) -> dict[str, Any]:
        """探活 runtime（Parlant REST /health）。"""
        async with self._client() as client:
            resp = await client.get(f"{self._base}/health")
            resp.raise_for_status()
            return resp.json()

    async def list_loaded(self) -> dict[str, Any]:
        """runtime 已加载 agent 列表。"""
        async with self._client() as client:
            resp = await client.get(f"{self._base}/internal/agents")
            resp.raise_for_status()
            return resp.json()

    async def runtime_info(self) -> dict[str, Any]:
        """运行时信息（模型/版本，供设置页展示；runtime 不可达时调用方应兜底）。"""
        async with self._client() as client:
            resp = await client.get(f"{self._base}/internal/info")
            resp.raise_for_status()
            return resp.json()

    # 加载（含旅程评估）可能跑数分钟：评估是多次 LLM 调用（草稿/新版本首次缓存未命中）。
    LOAD_TIMEOUT = 600.0

    async def load_agent(self, agent_id: str, definition: dict[str, Any]) -> dict[str, Any]:
        """把完整定义热加载进引擎（幂等）。"""
        async with self._client(timeout=self.LOAD_TIMEOUT) as client:
            resp = await client.post(
                f"{self._base}/internal/agents/{agent_id}/load",
                json={"definition": definition},
            )
            resp.raise_for_status()
            return resp.json()

    async def unload_agent(self, agent_id: str) -> dict[str, Any]:
        """卸载引擎实体。"""
        async with self._client() as client:
            resp = await client.post(f"{self._base}/internal/agents/{agent_id}/unload")
            resp.raise_for_status()
            return resp.json()

    async def override_variables(
        self,
        agent_id: str,
        customer_id: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        """按客户维度覆盖已加载 agent 实例的 Context Variable 值。

        转发 runtime `POST /internal/agents/{id}/variables/override`（按**变量名**解析引擎
        id → update_value(key=customer.id)）；用于模拟对话弹窗"设置变量覆盖 journey 配置"。
        """
        async with self._client() as client:
            resp = await client.post(
                f"{self._base}/internal/agents/{agent_id}/variables/override",
                json={"customer_id": customer_id, "variables": variables},
            )
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------ 会话代理（3.3）
    async def create_session(
        self,
        agent_id: str,
        customer_id: str,
        title: str | None = None,
    ) -> dict[str, Any]:
        """转发 Parlant `POST /sessions`；忽略客户端传入的 id（runtime 自生成）。"""
        body: dict[str, Any] = {"customer_id": customer_id, "agent_id": agent_id}
        if title:
            body["title"] = title
        async with self._client() as client:
            resp = await client.post(
                f"{self._base}/sessions?allow_greeting=false",
                json=body,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_session(self, session_id: str) -> dict[str, Any]:
        async with self._client() as client:
            resp = await client.get(f"{self._base}/sessions/{session_id}")
            resp.raise_for_status()
            return resp.json()

    async def list_sessions(self) -> list[dict[str, Any]]:
        async with self._client() as client:
            resp = await client.get(f"{self._base}/sessions")
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []

    async def create_customer(
        self,
        name: str,
        customer_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name}
        if customer_id:
            body["id"] = customer_id
        if metadata:
            body["metadata"] = metadata
        if tags:
            body["tags"] = tags
        async with self._client() as client:
            resp = await client.post(f"{self._base}/customers", json=body)
            resp.raise_for_status()
            return resp.json()

    async def list_customers(self) -> list[dict[str, Any]]:
        async with self._client() as client:
            resp = await client.get(f"{self._base}/customers")
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []

    async def post_event(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """转发 `POST /sessions/{id}/events`（如 {kind,source,message}）。"""
        async with self._client() as client:
            resp = await client.post(f"{self._base}/sessions/{session_id}/events", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def stream_events(
        self,
        session_id: str,
        *,
        min_offset: int = 0,
        wait_for_data: int = 60,
        source: str | None = None,
        kinds: str | None = None,
    ) -> AsyncIterator[bytes]:
        """订阅 runtime SSE（`sse=true`），逐块产出原始字节供上游转发。

        runtime 在 wait_for_data 内无新事件会自行关闭流；由调用方（StreamingResponse）
        负责把客户端断开（CancelledError）传递为停止消费，避免泄漏上游连接。
        """
        params: dict[str, Any] = {"sse": "true", "min_offset": min_offset, "wait_for_data": wait_for_data}
        if source:
            params["source"] = source
        if kinds:
            params["kinds"] = kinds
        async with self._client(timeout=None) as client:
            async with client.stream(
                "GET", f"{self._base}/sessions/{session_id}/events", params=params
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    yield chunk