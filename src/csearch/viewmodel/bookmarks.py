"""书签视图模型：保存 / 应用 / 重命名 / 删除（持久化与规则在 service 层）。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from csearch.models.entities import Bookmark
from csearch.models.enums import DialogKind

if TYPE_CHECKING:
    from csearch.viewmodel.context import AppContext


class BookmarksViewModel:
    """书签面板与对话框的交互逻辑。"""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._s = ctx.services
        self.state = ctx.state

    # ------------------------------------------------------------------ 保存
    def open_save_dialog(self) -> None:
        """打开「保存书签」对话框，名称默认取当前关键词。"""
        self.state.bm_edit_id = None
        self.state.bm_name = (self.state.query.strip() or "全部文件")[:40]
        self.state.dialog = DialogKind.BOOKMARK

    def confirm_save(self) -> None:
        self.state.bookmarks = self._s.bookmarks.add(
            self.state.bookmarks,
            self.state.bm_name,
            self.state.query,
            self.state.category,
            self.state.time_range,
            self.state.size_range,
        )
        self.state.dialog = None
        self._s.toast("书签已保存")

    # ------------------------------------------------------------------ 应用
    def apply(self, bookmark: Bookmark) -> None:
        """一键应用书签：回填搜索条件并查询。

        回填搜索框必须走 ``set_query``（程序化写入）：搜索框控件由 use_memo 持有，
        直接赋 ``state.query`` 不会把它同步到客户端输入框。
        """
        self.state.category = bookmark.category
        self.state.time_range = bookmark.time_range
        self.state.size_range = bookmark.size_range
        self._ctx.search.set_query(bookmark.query, run=False)
        asyncio.create_task(self._ctx.search.run_search())

    # ------------------------------------------------------------------ 重命名
    def open_rename_dialog(self, bookmark: Bookmark) -> None:
        self.state.bm_edit_id, self.state.bm_name = bookmark.id, bookmark.name
        self.state.dialog = DialogKind.BOOKMARK

    def confirm_rename(self) -> None:
        if not self.state.bm_edit_id:
            return
        self.state.bookmarks = self._s.bookmarks.rename(
            self.state.bookmarks, self.state.bm_edit_id, self.state.bm_name
        )
        self.state.dialog = None
        self._s.toast("书签已重命名")

    # ------------------------------------------------------------------ 删除
    def delete(self, bookmark: Bookmark) -> None:
        self.state.bookmarks = self._s.bookmarks.remove(
            self.state.bookmarks, bookmark.id
        )
        self._s.toast("书签已删除")
