"""A 类包：monkey-patch parlant SDK 内部（运行时 setattr 修订，非源码改动）。

按"对 SDK 的关系"分包（docs/04-execution-chain/04-parlant升级平移指南.md §1.2）：
本包是唯一修订 SDK 内部的包——升级 parlant 时逐一对照"锚点是否仍存在"
（patch_guard.py 在锚缺失时启动即失败，绝不静默失效）。

本 `__init__.py` 只承载包说明：**不放任何安装逻辑**；全部 patch 的统一安装入口在
`app.main.install_runtime_patches()`，新增 patch 时到该方法登记。

- ``patch_guard.py``       锚点断言（assert_anchor / PatchAnchorMissing）
- ``atomic_json_file.py``  评估缓存原子写（根治 kill -9 截断）
- ``journey_hash_stable.py`` 旅程评估稳定哈希（跨重启命中缓存）
- ``eval_model_split.py``  评估/对话模型分流（EVAL_LITELLM_*）+ 模型护栏
- ``do_generate.py``       DeepSeek 关 reasoning（按 provider 路由）+ gen_ai.chat span
- ``journey_eval_braces.py`` 旅程评估生成条件花括号转义（防模型抄录 `{var}` 致父节点 prompt format KeyError）
- ``next_step.py``         预留占位（未启用）
"""
