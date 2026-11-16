"""文件服务：编排文件系统动作，全部经线程池执行，返回结果而非触碰 UI。"""

from __future__ import annotations

import asyncio

from csearch.models.entities import ResultItem
from csearch.models.ports import FileOps


class FileService:
    """打开 / 定位 / 复制 / 删除 / 启动 Everything。"""

    def __init__(self, ops: FileOps) -> None:
        self._ops = ops

    async def open_items(self, items: list[ResultItem]) -> list[str]:
        return await asyncio.to_thread(self._ops.open_items, items)

    async def reveal_items(self, items: list[ResultItem]) -> list[str]:
        return await asyncio.to_thread(self._ops.reveal_items, items)

    async def copy_paths(self, items: list[ResultItem]) -> str | None:
        return await asyncio.to_thread(self._ops.copy_paths, items)

    async def copy_names(self, items: list[ResultItem]) -> str | None:
        return await asyncio.to_thread(self._ops.copy_names, items)

    async def delete_to_trash(
        self, items: list[ResultItem]
    ) -> tuple[list[str], list[str]]:
        return await asyncio.to_thread(self._ops.delete_to_trash, items)

    async def open_folder(self, path: str) -> str | None:
        return await asyncio.to_thread(self._ops.open_folder, path)

    def open_url(self, url: str) -> None:
        self._ops.open_url(url)

    def launch_everything(self) -> bool:
        """尝试启动 Everything（本地文件探测 + ShellExecute，毫秒级，同步即可）。"""
        return self._ops.launch_everything()
