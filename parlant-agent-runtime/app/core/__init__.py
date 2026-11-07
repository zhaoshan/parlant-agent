"""app.core：定义 → 引擎的装配核心（阶段2.3 起）。

拆分自 app/services/agent_loader.py（2026-11，766 行按内聚拆四）：
- ``loader``    AgentLoader 门面：幂等预删 → 装配 → 评估调度（公开 API 不变）
- ``builder``   AgentBuilder：定义 → SDK 实体装配线（glossary/canned/variables/
                journeys/guidelines/observations/relationships）
- ``evaluator`` AgentEvaluator：后台评估编排（旅程分叉表 + 指南元数据 + 模型护栏
                + 语义质检 + eval_status 登记）
- ``unloader``  AgentUnloader：级联删除（旅程级指南须 RelationshipStore 反查）
- ``helpers``   共用小工具与示例定义 IO

本 `__init__.py` 只承载包说明与门面导出，无业务逻辑（约定同 patches/extensions）。
"""

from app.core.loader import AgentLoader
from app.core.helpers import load_definition

__all__ = ["AgentLoader", "load_definition"]
