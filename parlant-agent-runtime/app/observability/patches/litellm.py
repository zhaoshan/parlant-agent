"""litellm monkey-patch：DeepSeek 关 reasoning + gen_ai.chat span（见 doc05 §3）。

一次 patch `LiteLLMSchematicGenerator.do_generate`，合并两项：
1. **DeepSeek 关 reasoning**（原 parlant `litellm_service.py` 必需 hack）：推理 token 耗尽
   max_tokens → content 空 → 引擎按 `{}` 处理 → schema 校验失败（表象=评估/匹配全挂）。
   注入 `hints["reasoning"]={"enabled": False}`（已把 `reasoning` 加进 supported_litellm_params）；
2. **gen_ai.chat span**（原 parlant `generation.py` 插桩，doc05 §2.1 的回退方案）：用 parlant
   tracer 开 `gen_ai.chat` span 记录 prompt/completion/usage → langfuse OTLP 摄入渲染为
   generation。**弃用 litellm OTel 回调的原因**：litellm 1.102 OpenTelemetry 集成在 async
   acompletion 下于 span 结束后仍调 set_attribute/set_status → 属性被丢弃 + stdout 刷屏
   （"Setting attribute on ended span."），实测不可用。parlant tracer 自己管理 span 生命周期，
   无此问题且嵌套关系与 process span 天然正确。
"""

from parlant.adapters.nlp.litellm_service import LiteLLMSchematicGenerator

_installed = False
_orig_do_generate = None  # install_litellm_patches() 里保存原 do_generate，调用期解析


async def _patched_do_generate(self, prompt, hints={}):  # noqa: B006 保持 parlant 原签名默认值
    # 1) DeepSeek 推理模型显式关 thinking（非推理模型忽略该参数，无副作用）
    if "deepseek" in self.model_name.lower():
        hints = {**hints, "reasoning": {"enabled": False}}

    # 2) gen_ai.chat span：prompt/completion/usage → langfuse generation
    try:
        prompt_str = prompt if isinstance(prompt, str) else prompt.build()
    except Exception:  # noqa: BLE001
        prompt_str = str(prompt)

    with self.tracer.span(
        "gen_ai.chat",
        attributes={
            "gen_ai.operation.name": "chat",
            "gen_ai.system": "litellm",
            "gen_ai.request.model": self.model_name,
            "gen_ai.prompt": prompt_str,
        },
    ):
        result = await _orig_do_generate(self, prompt, hints)
        try:
            completion = (
                result.content.model_dump_json()
                if hasattr(result.content, "model_dump_json")
                else str(result.content)
            )
        except Exception:  # noqa: BLE001
            completion = str(result.content)
        # parlant Tracer.attributes 是 contextmanager，须用 with 才真正写进 span
        # （原 parlant 插桩漏了 with，completion/usage 实际未生效——此处修正）
        with self.tracer.attributes({"gen_ai.completion": completion}):
            pass
        try:
            usage = result.info.usage
            with self.tracer.attributes(
                {
                    "gen_ai.usage.input_tokens": usage.input_tokens,
                    "gen_ai.usage.output_tokens": usage.output_tokens,
                }
            ):
                pass
        except Exception:  # noqa: BLE001
            pass
        return result


def install_litellm_patches() -> None:
    """DeepSeek 关 reasoning + gen_ai.chat span（幂等）。在 p.Server `__aenter__` 后调用。"""
    global _installed, _orig_do_generate
    if _installed:
        return

    # do_generate 里 `hints` 按 supported_litellm_params 筛选后透传给 acompletion；
    # 补上 "reasoning" 键，注入的 hints 才能进入 litellm_api_arguments。
    if "reasoning" not in LiteLLMSchematicGenerator.supported_litellm_params:
        LiteLLMSchematicGenerator.supported_litellm_params.append("reasoning")

    _orig_do_generate = LiteLLMSchematicGenerator.do_generate
    LiteLLMSchematicGenerator.do_generate = _patched_do_generate
    _installed = True
