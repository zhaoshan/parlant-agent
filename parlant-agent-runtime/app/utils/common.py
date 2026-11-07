"""通用工具（C 类）。与 SDK 无关的纯函数/小工具集中于此，随用随加。

用户文本常以 `{order_status}` 这类占位符风格书写，但 Parlant 的 PromptBuilder 对所有
section 模板执行 `template.format(**props)`——用户文本一旦被 f-string 拼进模板
（旅程步骤图、指南列表等），单花括号就被当成格式占位符 → KeyError → 评估/生成整体失败。

转义 `{`→`{{`、`}`→`}}` 后，`.format` 渲染结果仍是原文，LLM 看到的占位符不变。
仅用于"会被拼进 prompt 模板"的定义字段（loader 装配期调用）；**不要**用于 canned
response（Jinja2 模板，经 props 注入本就安全，转义会破坏 `{{generative.xxx}}` 变量）。
"""

from __future__ import annotations


def escape_braces(text: str | None) -> str | None:
    """`{`→`{{`、`}`→`}}`；None 原样返回。"""
    if text is None:
        return None
    return text.replace("{", "{{").replace("}", "}}")
