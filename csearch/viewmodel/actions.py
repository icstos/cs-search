"""文件动作视图模型：打开 / 定位 / 复制 / 删除 / 打开文件夹 / 运行次数 / 启动引擎。

全部系统调用交给 service 层入线程池；本层只负责「把结果翻译成状态与提示」，
删除默认移入回收站、无需确认，删除后本地即时移除并选中下一项，再后台重查同步。
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import TYPE_CHECKING

from csearch.models.constants import EVERYTHING_DOWNLOAD_URL
from csearch.models.entities import ResultItem
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
        """打开/设置次数后批量回查并刷新显示值（单次查询，避免逐行查库）。

        **必须换成新对象，不能原地改字段**（改前先读，这里踩过坑）：flet 的两道变更
        判定都走 `==` —— ``Observable.__setattr__`` 里的 ``value_equal``（不等才发通知）
        与 ``use_memo`` 里的 ``shallow_compare_args``（相等就复用上次的控件树）。
        旧实现是「原地改 row.run_count，再 state.results = list(state.results)」：改完
        之后新旧列表装的是同一批**已经改过的**对象，`==` 恒为真 → 不发通知、memo 不
        重算，界面上的次数永远停在旧值（数据库里其实早就加了）。症状就是
        「双击打开后次数没加一」。
        换新对象后三件事同时成立：`!=` 成立（发通知 + memo 重算）、行缓存键里的
        id 与次数都变了（只重建这一行）、未动的行保持同一性（其余行零重绘）。
        """
        touched = {p for p in paths if p}
        if not touched:
            return
        counts = await self._s.history.get_counts(touched)
        if not counts:
            return
        rows: list[ResultItem] = []
        changed = False
        for row in self.state.results:
            new_count = counts.get(row.full_path)
            if new_count is not None and new_count != row.run_count:
                rows.append(replace(row, run_count=new_count))
                changed = True
            else:
                rows.append(row)  # 次数没变：复用同一对象，该行控件零重建
        if changed:
            self.state.results = rows

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
            asyncio.create_task(self._ctx.search.sync_refresh())  # 原地重查，不跳回顶部

    # ------------------------------------------------------------------ 引擎引导
    def launch_everything(self) -> None:
        """一键启动 Everything；找不到程序则打开下载页。"""
        if self._s.files.launch_everything():
            self._s.toast("正在启动 Everything…")
        else:
            self._s.files.open_url(EVERYTHING_DOWNLOAD_URL)
