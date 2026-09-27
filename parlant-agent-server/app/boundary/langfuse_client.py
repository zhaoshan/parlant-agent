"""LangfuseClient——langfuse 公开 API 的数据读取客户端（httpx 异步）。

职责（链路历史 tab 数据源）：
- `get_trace_observations(trace_id)`：拉取指定 trace 的**全部** observation
  （扁平数组），供前端按 `parentObservationId` 组装执行链路树。
- 走 langfuse **Observations API v2**（高吞吐读端点，实测新组织下
  legacy `/api/public/traces` 不可用）：
      GET {base}/api/public/v2/observations?traceId=<id>&limit=1000
  Basic Auth（username=Public Key，password=Secret Key）；cursor 分页，
  循环取完所有页。
- 凭证由 server .env 提供（LANGFUSE_*），密钥只留在服务端，不下发浏览器。

网络约定：与 RuntimeClient 一致，`trust_env=False` 直连（本机 macOS 系统代理
会把 127.0.0.1/内网请求转代理导致 502；langfuse 是公网域名但保持一致避免
代理环境影响）。
"""

from __future__ import annotations

import base64
from typing import Any

import httpx


class LangfuseClient:
    def __init__(
        self,
        base_url: str,
        public_key: str,
        secret_key: str,
        timeout: float = 30.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._auth = (
            base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
            if public_key and secret_key
            else None
        )
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        """是否已配置 langfuse 凭证（未配置时链路历史端点返回 503 提示）。"""
        return bool(self._base and self._auth)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Basic {self._auth}"}

    async def get_trace_observations(self, trace_id: str) -> list[dict[str, Any]]:
        """拉取一个 trace 的全部 observation（扁平数组，cursor 分页取完）。

        显式请求全部分组字段（`fields`），否则 v2 端点默认只回 core+basic
        （缺 input/output/model/usage/metadata 等详情字段）。
        """
        observations: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {
                "traceId": trace_id,
                "limit": 1000,
                "fields": "core,basic,time,io,metadata,model,usage,prompt,metrics,trace_context",
            }
            if cursor:
                params["cursor"] = cursor
            async with httpx.AsyncClient(
                trust_env=False, timeout=self._timeout
            ) as client:
                resp = await client.get(
                    f"{self._base}/api/public/v2/observations",
                    params=params,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                body = resp.json()
            observations.extend(body.get("data") or [])
            cursor = (body.get("meta") or {}).get("cursor")
            if not cursor:
                break
        return observations
