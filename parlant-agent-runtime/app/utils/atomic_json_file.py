"""JSONFileDocumentDatabase 非原子写 → 原子写（根治截断）。

背景（2026-10-21 定位）：SDK 的 `_save_data` 用 `mode="w"` **先截断再写**（非原子）——进程在
写入窗口被 `kill -9`/崩溃会留下 0 字节/半截文件；而 `_load_raw_data` 把 0 字节文件**静默当空缓存**
（`st_size==0 → {}`），下次启动"缓存消失 → 全量重评估"（评估缓存 / doc11 附录）。

根治：monkey-patch 成**原子写**——先写同目录临时文件 + fsync + `os.replace`（POSIX 原子替换），
文件永远是"旧版完整"或"新版完整"，绝不出现半截/空文件。顺带把 `_load_raw_data` 的空文件分支
改成打 warning（万一再发生也可见）。

遵循项目"Parant 源码改动最小、hack 归 runtime 持有"（同 `app/utils/observability.py`）：不改
parlant 源码，运行时装配期幂等安装。
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping, Sequence
from typing import Any

import aiofiles

logger = logging.getLogger(__name__)

_PATCHED = False


async def _atomic_save_data(
    self: Any, data: Mapping[str, Sequence[Mapping[str, Any]]]
) -> None:
    """原子写：临时文件 + flush/fsync + os.replace。调用方持 writer_lock（并发安全）。"""
    tmp_path = self.file_path.with_name(f"{self.file_path.name}.tmp")
    async with aiofiles.open(tmp_path, mode="w", encoding="utf-8") as file:
        await file.write(
            json.dumps({**self._raw_data, **data}, ensure_ascii=False, indent=2)
        )
        await file.flush()
        os.fsync(file.fileno())
    os.replace(tmp_path, self.file_path)  # 同目录原子替换：旧完整或新完整，绝无半截


async def _load_raw_data_with_warn(self: Any) -> dict[str, Any]:
    """原逻辑 0 字节静默返回 {}；改为打 warning 提示（原子写后一般不再发生）。"""
    if self.file_path.stat().st_size == 0:
        logger.warning("[json-file] %s 为空（0 字节）：缓存丢失将触发全量重评估", self.file_path)
        return {}
    async with aiofiles.open(self.file_path, "r", encoding="utf-8") as file:
        return json.loads(await file.read())


def install_atomic_json_file_write() -> None:
    """幂等安装：替换 `JSONFileDocumentDatabase._save_data/_load_raw_data` 为原子写版本。"""
    global _PATCHED
    if _PATCHED:
        return
    from parlant.adapters.db.json_file import JSONFileDocumentDatabase

    JSONFileDocumentDatabase._save_data = _atomic_save_data
    JSONFileDocumentDatabase._load_raw_data = _load_raw_data_with_warn
    _PATCHED = True
    logger.info("[json-file] 已安装原子写 patch（临时文件 + os.replace，根治截断）")