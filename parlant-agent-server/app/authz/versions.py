"""IAM 成员令牌版本点查（user-manual §6 方案① / doc11 附录B 方案 c）。

逐请求即时吊销：`GatewayProvider` 验签后，用 token 的 `membershipId`+`ver` 点查 IAM
`GET /api/v1/auth/versions?app_code=<audience>&membership_id=<id>`（`X-IAM-Service-Token` 鉴权），
返回 `items[0].version`——`-1`（tombstone，成员删除/未知，IAM 保守）或 `> token.ver`（权限已变更）→ 401，
由调用方转 `AuthError`；配合附录 A 静默刷新无感续期（401 → refresh 换带新 ver 的 token → 重试）。

方案① 的显式代价 = **每请求一跳 IAM（可用性耦合）**：点查失败（网络/非 200）→ fail-closed 抛错，
由调用方转 502（区别于"权限已变更"的 401，避免触发前端刷新/重登）。
仅当 `iam_versions_url` + `iam_versions_token` 都配置才启用（否则关闭、零开销）。
"""

from __future__ import annotations

import logging
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


class TokenVersionGuard:
    """按 membership_id 点查 IAM 当前 token 版本（方案① 每请求点查）。"""

    def __init__(
        self, *, versions_url: str, service_token: str, app_code: str, timeout: float = 3.0
    ) -> None:
        self._url = versions_url.rstrip("/")
        self._token = service_token
        self._app_code = app_code
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self._url and self._token)

    def check(self, membership_id: str, token_ver: int) -> None:
        """未启用或无 membership → 直接通过。

        落后（IAM 当前版本 > token.ver）或 tombstone(-1，成员删除/未知) → 抛 `PermissionError`；
        IAM 不可达/非 200 → 抛 `ConnectionError`/`RuntimeError`（fail-closed，可用性耦合）。
        """
        if not self.enabled or not membership_id:
            return
        try:
            resp = httpx.get(
                f"{self._url}?app_code={quote(self._app_code)}&membership_id={quote(membership_id)}",
                headers={"X-IAM-Service-Token": self._token},
                timeout=self._timeout,
                trust_env=False,  # 服务间 127.0.0.1 直连，防 macOS 系统代理劫持（CLAUDE.md §5.4）
            )
        except httpx.HTTPError as exc:
            logger.warning("[authz] IAM 版本点查失败（%s）: %s", self._url, exc)
            raise ConnectionError(f"IAM 版本校验不可达：{type(exc).__name__}: {exc}") from exc
        if resp.status_code != 200:
            logger.warning("[authz] IAM 版本点查非 200: %s %s", resp.status_code, resp.text[:120])
            raise RuntimeError(f"IAM 版本校验返回 {resp.status_code}")
        items = (resp.json().get("items") or [])
        if not items:
            return  # IAM 未见该成员：token 已过 JWKS 验签，放行避免误伤（tombstone 由 IAM 显式下发）
        current = int(items[0].get("version", 0))
        if current == -1 or current > token_ver:
            raise PermissionError("权限已变更，请重新登录")