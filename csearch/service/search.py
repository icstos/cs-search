"""搜索服务：编排「查询构建 → 分页检索 → 运行次数回填」的完整流程。

只依赖 ``SearchEngine`` / ``RunHistory`` 两个抽象端口，不感知 Everything SDK、
SQLite 或 everytools 的存在。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from csearch.models.constants import PAGE_SIZE
from csearch.models.entities import EngineStatus, SearchOutcome
from csearch.models.ports import RunHistory, SearchEngine


class SearchService:
    """查询编排（同步端口调用统一经线程池执行，不阻塞事件循环）。"""

    def __init__(self, engine: SearchEngine, history: RunHistory) -> None:
        self._engine = engine
        self._history = history

    # ------------------------------------------------------------------ 状态
    @property
    def version(self) -> str:
        return self._engine.version

    @property
    def available(self) -> bool:
        return self._engine.available

    @property
    def error_message(self) -> str:
        return self._engine.error_message

    @property
    def notify_registered(self) -> bool:
        return self._engine.notify_registered

    async def check_status(self) -> EngineStatus:
        return await asyncio.to_thread(self._engine.check_status)

    # ------------------------------------------------------------------ 查询构建
    def build_query(
        self,
        keyword: str,
        category: str,
        time_range: str,
        size_range: str,
        regex: bool = False,
    ) -> str:
        return self._engine.build_query(keyword, category, time_range, size_range, regex)

    def sort_value(self, column: str, desc: bool) -> int:
        return self._engine.sort_value(column, desc)

    # ------------------------------------------------------------------ 分页检索
    async def search_page(
        self, query: str, sort_val: int, offset: int = 0, count: int = PAGE_SIZE
    ) -> SearchOutcome:
        """一次线程池往返内完成「分页查询 + 运行次数回填」。

        原先 search 与 get_counts 各占一次线程往返，界面上表现为结果集到了却还要
        再等一个来回才落地。合并后只剩一次切换；顺带补上增量加载分页的运行次数
        （原先只有首页回填，后续页的「次数」列恒为空）。
        """
        return await asyncio.to_thread(self._query_page, query, sort_val, offset, count)

    def _query_page(
        self, query: str, sort_val: int, offset: int, count: int
    ) -> SearchOutcome:
        outcome = self._engine.search(query, sort_val, offset, count)
        counts = self._history.get_counts(r.full_path for r in outcome.rows)
        if counts:
            for row in outcome.rows:
                row.run_count = counts.get(row.full_path, 0)
        return outcome

    # ------------------------------------------------------------------ 索引监听
    def start_change_monitor(self, callback: Callable[[], None]) -> None:
        self._engine.start_change_monitor(callback)

    def stop_change_monitor(self) -> None:
        self._engine.stop_change_monitor()

    def try_register_notify_window(self, hwnd: int, msg_id: int) -> bool:
        return self._engine.try_register_notify_window(hwnd, msg_id)
