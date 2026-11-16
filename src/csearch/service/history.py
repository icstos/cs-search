"""运行历史服务：把同步的 SQLite 仓储包装成非阻塞的异步 API。"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from csearch.models.ports import RunHistory


class HistoryService:
    """运行次数读写（全部走线程池，避免同步 IO 顶住事件循环）。"""

    def __init__(self, repo: RunHistory) -> None:
        self._repo = repo

    async def init(self) -> None:
        await asyncio.to_thread(self._repo.init_db)

    def init_blocking(self) -> None:
        """后台线程内直接建表（供启动装配使用）。"""
        self._repo.init_db()

    async def get_counts(self, paths: Iterable[str]) -> dict[str, int]:
        return await asyncio.to_thread(self._repo.get_counts, list(paths))

    async def increment(self, paths: Iterable[str]) -> None:
        await asyncio.to_thread(self._repo.increment, list(paths))

    async def set_count(self, path: str, count: int) -> None:
        await asyncio.to_thread(self._repo.set_count, path, count)
