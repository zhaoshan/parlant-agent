"""patches 包门面：monkey-patch 集中层（替代散落 parlant 源码的模型适配 / LLM I/O 观测）。

- ``litellm``：`install_litellm_patches()` —— DeepSeek 关 reasoning + gen_ai.chat span（启用）
- ``next_step``：预留 next_step 命中条件日志 patch（doc12 §2.3，先弃，默认不启用）
"""

from app.observability.patches.litellm import install_litellm_patches

__all__ = ["install_litellm_patches"]
