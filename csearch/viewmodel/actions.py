"""文件动作视图模型：打开 / 定位 / 复制 / 删除 / 打开文件夹 / 运行次数 / 启动引擎。

全部系统调用交给 service 层入线程池；本层只负责「把结果翻译成状态与提示」，
删除默认移入回收站、无需确认，删除后本地即时移除并选中下一项，再后台重查同步。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from csearch.models.constants import EVERYTHING_DOWNLOAD_URL
from csearch.models.enums import DialogKind

if TYPE_CHECKING:
    from csearch.viewmodel.context import AppContext


class ActionsViewModel:
    """结果相关的用户动作。"""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._s = ctx.services
        self.state = ctx.state

    # ------------------------------------------------------------------ 运行次数
    def request_run_count(self, index: int) -> None:
        """右键设置运行次数：打开输入对话框。"""
        if 0 <= index < len(self.state.results):
            item = self.state.results[index]
            self.state.run_count_path = item.full_path
            self.state.run_count_text = str(item.run_count)
            self.state.dialog = DialogKind.RUN_COUNT

    def confirm_run_count(self) -> None:
        """确认设置运行次数（写库与回查放后台，避免点「确定」时卡一下）。"""
        try:
            count = max(0, int(self.state.run_count_text.strip() or "0"))
        except ValueError:
            self._s.toast("请输入有效的非负整数")
            return
        if not self.state.run_count_path:
            return
        asyncio.create_task(self._apply_run_count(self.state.run_count_path, count))

    async def _apply_run_count(self, path: str, count: int) -> None:
        await self._s.history.set_count(path, count)
        await self._refresh_run_counts([path])
        self.state.dialog = None
        self._s.toast(f"已设置运行次数：{count}")

    async def _refresh_run_counts(self, paths: list[str]) -> None:
        """打开/设置次数后批量回查并本地更新显示值（单次查询，避免逐行查库）。"""
        touched = {p for p in paths if p}
        if not touched:
            return
        counts = await self._s.history.get_counts(touched)
        changed = False
        for row in self.state.results:
            if row.full_path in touched:
                row.run_count = counts.get(row.full_path, row.run_count)
                changed = True
        if changed:
            self.state.results = list(self.state.results)  # 整体替换触发重绘

    # ------------------------------------------------------------------ 文件动作
    async def open_selected(self) -> None:
        items = self._ctx.selection.selected_items()
        if not items:
            self._s.toast("未选中任何文件")
            return
        errors = await self._s.files.open_items(items)
        if errors:
            self._s.toast(f"打开失败：{errors[0]}")
            return
        opened = [i.full_path for i in items]
        await self._s.history.increment(opened)
        await self._refresh_run_counts(opened)

    async def reveal_selected(self) -> None:
        items = self._ctx.selection.selected_items()
        if not items:
            self._s.toast("未选中任何文件")
            return
        errors = await self._s.files.reveal_items(items)
        if errors:
            self._s.toast(f"定位失败：{errors[0]}")

    async def copy_paths(self) -> None:
        items = self._ctx.selection.selected_items()
        if not items:
            self._s.toast("未选中任何文件")
            return
        error = await self._s.files.copy_paths(items)
        self._s.toast(
            f"复制失败：{error}" if error else f"已复制 {len(items)} 个完整路径"
        )

    async def copy_names(self) -> None:
        items = self._ctx.selection.selected_items()
        if not items:
            self._s.toast("未选中任何文件")
            return
        error = await self._s.files.copy_names(items)
        self._s.toast(f"复制失败：{error}" if error else f"已复制 {len(items)} 个文件名")

    async def open_folder(self, index: int) -> None:
        """双击路径列：在资源管理器中打开对应文件夹。"""
        if 0 <= index < len(self.state.results):
            error = await self._s.files.open_folder(self.state.results[index].path)
            if error:
                self._s.toast(f"打开文件夹失败：{error}")

    async def delete_selected(self) -> None:
        """删除选中项到回收站（无需确认），本地即时移除并选中下一项，随后后台重查同步。"""
        items = self._ctx.selection.selected_items()
        if not items:
            self._s.toast("未选中任何文件")
            return
        first = min(self.state.selected)  # 首个被删行位置：移除后该位置即「下一项」
        deleted_paths, errors = await self._s.files.delete_to_trash(items)
        if deleted_paths:
            gone = set(deleted_paths)
            self.state.results = [
                r for r in self.state.results if r.full_path not in gone
            ]
            self.state.total = max(0, self.state.total - len(deleted_paths))
            if self.state.results:
                target = min(first, len(self.state.results) - 1)
                self.state.selected, self.state.anchor = {target}, target
                asyncio.create_task(self._ctx.search.scroll_results(row=target))
            else:
                self.state.selected, self.state.anchor = set(), -1
        self._s.toast(
            f"已移入回收站 {len(deleted_paths)} 项"
            + (f"，失败：{errors[0]}" if errors else "")
        )
        if deleted_paths:
            asyncio.create_task(self._ctx.search.run_search(keep_selection=True))

    # ------------------------------------------------------------------ 引擎引导
    def launch_everything(self) -> None:
        """一键启动 Everything；找不到程序则打开下载页。"""
        if self._s.files.launch_everything():
            self._s.toast("正在启动 Everything…")
        else:
            self._s.files.open_url(EVERYTHING_DOWNLOAD_URL)
