"""鉴权异常：Provider 认证失败时抛出，中间件据此返回对应状态码。"""

from __future__ import annotations


class AuthError(Exception):
    """认证失败。`status_code` 决定中间件返回：401=未认证/凭证无效，403=已认证但不可用。"""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail