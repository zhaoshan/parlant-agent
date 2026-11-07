"""评估/对话模型分流：评估链路用独立配置的模型（EVAL_LITELLM_*），对话模型随意换。

评估管线对模型 JSON/schema 遵从要求极高（幻觉元数据会致旅程静默卡死），对话模型则需
按成本/效果灵活切换；SDK 单 NLPService 无法 plumbing 级拆分，本 patch 类级 monkey-patch
`LiteLLMService.get_schematic_generator` 达同样效果，零源码改动。

- schema ∈ EVAL_SCHEMAS（评估管线全部 7 个，逐一核对 indexing 模块）且配置了
  EVAL_LITELLM_MODEL_NAME → 用评估配置构造生成器；否则透传主服务。引擎运行时 schema
  （匹配/next-step/消息）不在列，仍走对话模型。
- api_key：上游 do_generate 每调用读全局 env，无法按实例区分——评估生成器包
  `_KeyedClient` 覆盖 acompletion 的 api_key kwarg。
- 未配置 EVAL_LITELLM_MODEL_NAME → 纯透传（向后兼容）。

模型护栏（eval_model_proven）与本 patch 同文件；锚点断言见 patch_guard。
"""

from __future__ import annotations

import structlog
import os
from typing import Any

logger = structlog.get_logger()

_PATCHED = False

# BehavioralChangeEvaluator 评估管线的全部 schema（indexing 模块逐一核对，勿漏——
# 漏一个 = 该子任务仍走对话模型 = 评估质量缺口）
EVAL_SCHEMAS: tuple[type, ...] = ()

_EVAL_MODEL_ENV = "EVAL_LITELLM_MODEL_NAME"
_EVAL_BASE_URL_ENV = "EVAL_LITELLM_BASE_URL"
_EVAL_API_KEY_ENV = "EVAL_LITELLM_API_KEY"

# —— 评估模型护栏（fail-closed，与 loader 的评估流程配合）——
# 评估元数据只能由验证过的模型产出。缓存 miss 且生效评估模型不在名单 → 拒绝评估（blocked）
# + 响亮告警，宁可不评也不让幻觉元数据落缓存（10-21 投顾卡节点 3 事故）。
# 名单经 env EVAL_PROVEN_MODEL_MARKERS 配置（逗号分隔），见 proven_eval_model_markers()。
_EVAL_PROVEN_MARKERS_ENV = "EVAL_PROVEN_MODEL_MARKERS"
_DEFAULT_PROVEN_MARKERS = "deepseek-ai/DeepSeek-V4-Flash"


def proven_eval_model_markers() -> tuple[str, ...]:
    """评估模型验证名单（env 逗号分隔；缺省/置空 → SiliconFlow DeepSeek-V4-Flash）。

    用函数而非常量：模块 import 早于 .env 装载（main 的 get_settings 才 load_dotenv），
    必须调用期读取——与 _eval_cfg()/current_eval_model() 同模式。
    """
    raw = os.getenv(_EVAL_PROVEN_MARKERS_ENV) or _DEFAULT_PROVEN_MARKERS
    return tuple(m.strip() for m in raw.split(",") if m.strip())


def current_eval_model() -> str:
    """生效的评估模型名：配置了 EVAL_LITELLM_MODEL_NAME（本 patch 分流）查它，
    否则评估与对话共用主模型、查 LITELLM_PROVIDER_MODEL_NAME。"""
    return os.getenv(_EVAL_MODEL_ENV, "").strip() or os.getenv("LITELLM_PROVIDER_MODEL_NAME", "")


def eval_model_proven() -> bool:
    """当前评估模型是否在验证名单（settings.eval_model_guard=off 时恒通过）。"""
    from app.config import get_settings

    if not get_settings().eval_model_guard:
        return True
    model = current_eval_model()
    return any(marker in model for marker in proven_eval_model_markers())


def _eval_cfg() -> dict[str, str] | None:
    """评估模型配置；未配置 EVAL_LITELLM_MODEL_NAME（或缺 base_url）→ None=透传。"""
    model = os.getenv(_EVAL_MODEL_ENV, "").strip()
    if not model:
        return None
    base_url = os.getenv(_EVAL_BASE_URL_ENV, "").strip()
    if not base_url:
        logger.warning(
            "[eval-model-split] %s 已配置但 %s 为空——按透传处理（评估仍走对话模型）",
            _EVAL_MODEL_ENV, _EVAL_BASE_URL_ENV,
        )
        return None
    return {"model": model, "base_url": base_url, "api_key": os.getenv(_EVAL_API_KEY_ENV, "").strip()}


class _KeyedClient:
    """litellm 模块包装：force-override api_key（其余属性直通真模块）。

    上游 do_generate 每调用读全局 env LITELLM_PROVIDER_API_KEY 并以显式 kwarg 传给
    acompletion——并发下无法按实例区分 key；这里在 client 层覆盖 kwargs。
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        import litellm

        self._real = litellm

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    async def acompletion(self, *args: Any, **kwargs: Any) -> Any:
        if self._api_key:
            kwargs["api_key"] = self._api_key
        return await self._real.acompletion(*args, **kwargs)


async def _patched_get_schematic_generator(self: Any, t: type, hints: dict | None = None) -> Any:
    """分流：评估 schema → EVAL_LITELLM_* 构建的生成器；其余 → 原样（对话模型）。"""
    if EVAL_SCHEMAS and t in EVAL_SCHEMAS and (cfg := _eval_cfg()):
        from parlant.adapters.nlp.litellm_service import LiteLLM_Default

        # 照抄 LiteLLMService.get_schematic_generator 原函数体的构造形状
        generator = LiteLLM_Default[t](  # type: ignore[index]
            self.logger,
            self._tracer,
            self._meter,
            self._health_reporter,
            cfg["base_url"],
            cfg["model"],
        )
        generator._client = _KeyedClient(cfg["api_key"])
        logger.info(
            "[eval-model-split] schema %s 走评估模型 %s (%s)",
            getattr(t, "__name__", t), cfg["model"], cfg["base_url"],
        )
        return generator
    return await _orig_get_schematic_generator(self, t, hints)


_orig_get_schematic_generator = None  # install 时保存原方法


def install_eval_model_split() -> None:
    """幂等安装：分流评估 schema 到 EVAL_LITELLM_* 配置的模型（须在 p.Server 装配前调用）。"""
    global _PATCHED, _orig_get_schematic_generator, EVAL_SCHEMAS
    if _PATCHED:
        return
    from parlant.adapters.nlp.litellm_service import LiteLLMService
    from parlant.core.services.indexing.customer_dependent_action_detector import (
        CustomerDependentActionSchema,
    )
    from parlant.core.services.indexing.guideline_action_proposer import (
        GuidelineActionPropositionSchema,
    )
    from parlant.core.services.indexing.guideline_agent_intention_proposer import (
        AgentIntentionProposerSchema,
    )
    from parlant.core.services.indexing.guideline_continuous_proposer import (
        GuidelineContinuousPropositionSchema,
    )
    from parlant.core.services.indexing.journey_reachable_nodes_evaluation import (
        ReachableNodesEvaluationSchema,
    )
    from parlant.core.services.indexing.relative_action_proposer import RelativeActionSchema
    from parlant.core.services.indexing.tool_running_action_detector import (
        ToolRunningActionSchema,
    )

    from app.patches.patch_guard import assert_anchor

    assert_anchor(LiteLLMService, "get_schematic_generator", patch="eval-model-split",
                  hint="上游生成器装配重构时需同步本 patch（照抄新装配逻辑）。")

    EVAL_SCHEMAS = (
        AgentIntentionProposerSchema,
        CustomerDependentActionSchema,
        GuidelineActionPropositionSchema,
        GuidelineContinuousPropositionSchema,
        ReachableNodesEvaluationSchema,
        RelativeActionSchema,
        ToolRunningActionSchema,
    )

    _orig_get_schematic_generator = LiteLLMService.get_schematic_generator
    LiteLLMService.get_schematic_generator = _patched_get_schematic_generator
    _PATCHED = True
    cfg = _eval_cfg()
    logger.info(
        "[eval-model-split] 已安装：%s",
        f"评估模型={cfg['model']}@{cfg['base_url']}" if cfg else "未配置 EVAL_LITELLM_*，纯透传",
    )
