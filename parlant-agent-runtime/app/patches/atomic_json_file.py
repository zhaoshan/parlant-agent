"""JSONFileDocumentDatabase 原子写（根治 kill -9 截断缓存文件）。

SDK `_save_data` 用 mode="w" 先截断再写（非原子），写入窗口被杀留 0 字节/半截文件；
`_load_raw_data` 把 0 字节静默当空缓存 → 重启全量重评估。本 patch 换成临时文件 + fsync +
os.replace（POSIX 原子替换），文件永远新旧完整其一；空文件读改打 warning（再发生可见）。

须在 p.Server 装配前幂等安装（入口 app.main.install_runtime_patches）。
"""

from __future__ import annotations

import structlog
import json
import os
from collections.abc import Mapping, Sequence
from typing import Any

import aiofiles

logger = structlog.get_logger()

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

    from app.patches.patch_guard import assert_anchor

    assert_anchor(JSONFileDocumentDatabase, "_save_data", patch="atomic-json-file",
                  hint="上游若已改原子写，可整包删除本 patch。")
    assert_anchor(JSONFileDocumentDatabase, "_load_raw_data", patch="atomic-json-file")
    JSONFileDocumentDatabase._save_data = _atomic_save_data
    JSONFileDocumentDatabase._load_raw_data = _load_raw_data_with_warn
    _PATCHED = True
    logger.info("[json-file] 已安装原子写 patch（临时文件 + os.replace，根治截断）")