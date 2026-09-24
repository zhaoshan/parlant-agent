"""鉴权 / CORS 策略（configure_container 用）。

阶段1：开发环境放行一切（DevelopmentAuthorizationPolicy 自带 CORS *），便于前端联调。
阶段5：替换为 ProductionAuthorizationPolicy（JWT + operation 级授权 + CORS 收紧）。
对应 docs/03-production/04-API增强.md。
"""

from lagom import Container
import parlant.sdk as p


async def build_container(container: Container) -> Container:
    """p.Server(configure_container=...) 的回调：覆盖 DI 容器里的鉴权策略。"""
    container[p.AuthorizationPolicy] = p.DevelopmentAuthorizationPolicy()
    return container
