"""monkey-patch 锚点断言：锚点缺失 → 启动即失败（防 parlant 升级后静默失效）。

patch 以方法/属性名为锚 setattr 到 SDK 内部类：升级后锚点改名/移除时，setattr 会静默
装上永不被调用的方法，行为退化且无任何报错。install 期做存在性硬校验，把静默失效变成
响亮失败。硬失败而非告警：上游若已修复对应问题，正确动作也是删除该 install。

用法：每个 install_*() 在 setattr 前调用 assert_anchor()。
详见 docs/04-execution-chain/04-parlant升级平移指南.md。
"""

from __future__ import annotations

from typing import Any


class PatchAnchorMissing(RuntimeError):
    """parlant 升级后 patch 锚点（方法/属性名）不存在——对应 patch 需同步或删除。"""


def assert_anchor(target: Any, anchor: str, *, patch: str, hint: str = "") -> None:
    """校验锚点存在；缺失抛 PatchAnchorMissing（启动即失败）。

    :param target: 被 patch 的 SDK 类（已 import 的对象）。
    :param anchor: 方法/属性名。
    :param patch: patch 名（出现在报错里，便于定位 install_*）。
    :param hint: 补充处置提示（如"上游若已修复可删除本 patch"）。
    """
    if not hasattr(target, anchor):
        raise PatchAnchorMissing(
            f"[patch-guard] {patch}：锚点 '{anchor}' 在 {target.__name__} 上不存在——"
            f"parlant 升级后内部结构已变更，该 patch 已静默失效。\n"
            f"处置：同步补丁实现；若上游已修复对应问题则删除该 install 调用。"
            f"参考 docs/04-execution-chain/04-parlant升级平移指南.md。{hint}"
        )
