"""do_generate 拦截：DeepSeek 关 reasoning + gen_ai.chat 观测 span（替代原源码插桩）。

patch `LiteLLMSchematicGenerator.do_generate`，合并两项：
1. **DeepSeek 关 reasoning**：推理 token 耗尽 max_tokens → content 空 → 评估/匹配全挂。
   "关思考"是各家私有扩展，按 base_url 路由——OpenRouter 认 reasoning={"enabled": False}
   （已实测：reasoning_tokens 归 0）；其他网关约定未验证，暂不注入（防严格网关 400）。
   注入键已加进 supported_litm_params 白名单（否则到不了 litellm）。
2. **gen_ai.chat span**：parlant tracer 开 span 记录 prompt/completion/usage → langfuse
   generation。弃用 litellm OTel 回调（async 下 ended-span 属性丢失 + stdout 刷屏，实测不可用）。
"""

from parlant.adapters.nlp.litellm_service import LiteLLMSchematicGenerator

_installed = False
_orig_do_generate = None  # install_litellm_patches() 里保存原 do_generate，调用期解析


async def _patched_do_generate(self, prompt, hints={}):  # noqa: B006 保持 parlant 原签名默认值
    # 1) DeepSeek 推理模型显式关 thinking——"关思考"是各家私有扩展，无跨 provider 统一参数，
    #    按 provider 路由（2026-11-07 OpenRouter 实测：无参时 reasoning_tokens 占输出 81%，
    #    注入 reasoning={"enabled": False} 后归零——就是它当年吃光 max_tokens 致空 content 的元凶；
    #    而 Qwen 系的 enable_thinking 被 OpenRouter 忽略）：
    #    - OpenRouter 网关 → 注入 reasoning={"enabled": False}
    #    - SiliconFlow 等其他网关 → 暂不注入（参数约定未验证；严格校验网关可能对未知参数
    #      400——eval_model_split 后评估请求会首次发往非 OpenRouter，验证后在此补分支）
    if "deepseek" in self.model_name.lower():
        base = (self.base_url or "").lower()
        if "openrouter" in base:
            hints = {**hints, "reasoning": {"enabled": False}}
        elif "api.deepseek.com" in base:
            # DeepSeek 官方：flash 是思考型模型（小 prompt 思考约占 2/3 token；relative
            # action 大 prompt 思考烧光 max_tokens → content 空 → 评估失败，2026-11-07 实测）。
            # 官方关思考参数 thinking 经 extra_body 透传（litellm 不识别顶层 thinking 会
            # 拒收；extra_body 已加 supported_litm_params 白名单），实测 reasoning 归零。
            extra_body = {**hints.get("extra_body", {}), "thinking": {"type": "disabled"}}
            hints = {**hints, "extra_body": extra_body}

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
    """DeepSeek 关 reasoning + gen_ai.chat span（幂等）。

    经 app.main.install_runtime_patches() 在 p.Server 装配前统一调用（类级 patch，
    装配期只构造生成器、不触发生成，提前安装安全）。
    """
    global _installed, _orig_do_generate
    if _installed:
        return

    from app.patches.patch_guard import assert_anchor

    assert_anchor(LiteLLMSchematicGenerator, "do_generate", patch="observability/litellm",
                  hint="do_generate 签名/行为变化时需同步 _patched_do_generate。")
    # do_generate 里 hints 按 supported_litellm_params 筛选后透传给 acompletion，补白名单键：
    # reasoning=OpenRouter 关思考；extra_body=DeepSeek 官方关思考（thinking 透传体）。
    for key in ("reasoning", "extra_body"):
        if key not in LiteLLMSchematicGenerator.supported_litellm_params:
            LiteLLMSchematicGenerator.supported_litellm_params.append(key)

    _orig_do_generate = LiteLLMSchematicGenerator.do_generate
    LiteLLMSchematicGenerator.do_generate = _patched_do_generate
    _installed = True
