"""labels 包门面：journey index → 节点名称（BFS 复刻 parlant 投影，见 ``journey_labels`` 模块）。"""

from app.observability.labels.journey_labels import JourneyLabelResolver, journey_labels

__all__ = ["journey_labels", "JourneyLabelResolver"]
