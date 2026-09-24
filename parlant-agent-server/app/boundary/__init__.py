"""boundary 包：下游 parlant-agent-runtime 的 HTTP 客户端 + 防腐层。"""

from app.boundary.runtime_client import RuntimeClient

__all__ = ["RuntimeClient"]