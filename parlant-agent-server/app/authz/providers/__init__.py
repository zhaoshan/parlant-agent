"""AuthProvider 实现：dev（本地免认证）/ gateway（IAM RS256+JWKS）。

jwt（HS256 本地自签发）已随"登录页收归 IAM hub"淘汰（2026-10-11，doc11 形态 B）——
无入口发/取 token；生产只有 gateway。若未来需独立部署可接 OIDC 直连客户 IdP，不自管 HS256。
"""

from app.authz.providers.dev import DevProvider
from app.authz.providers.gateway import GatewayProvider

__all__ = ["DevProvider", "GatewayProvider"]
