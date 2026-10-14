"""选中与导航视图模型：单击多选 / 双击分发 / 键盘移动 / 焦点域切换。

双击判定说明：
- 同一个 GestureDetector 上 ``on_tap`` + ``on_double_tap`` 互斥（双击只触发
  ``on_double_tap``，会牺牲单击响应的即时性），因此沿用「同一行在系统双击时间窗内
  二次 on_tap」的手动判定，单击选中零延迟；
- 时间窗取系统 ``GetDoubleClickTime()``（默认 500ms），写死小值会漏判系统认可的
  稍慢双击；
- 按列分发：路径列双击打开所在文件夹（对齐 Everything），其余列双击打开条目本身。
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from csearch.models.entities import ResultItem
from csearch.models.enums import Focus

if TYPE_CHECKING:
    from csearch.viewmodel.context import AppContext


class SelectionViewModel:
    """结果选中、键盘导航与焦点域管理。"""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._s = ctx.services
        self.state = ctx.state
        # 双击判定：上次点击行与时刻（跨行控件重建仍然有效）
        self._last_click_index = -1
        self._last_click_time = 0.0

    # ------------------------------------------------------------------ 焦点域
    def focus_search(self) -> None:
        """把键盘焦点切回搜索框（focus_epoch+1 触发 key 重挂载以实现 autofocus）。"""
        self.state.focus = Focus.SEARCH
        self.state.focus_epoch += 1

    def focus_list(self) -> None:
        """把键盘焦点切到结果列表。"""
        self.state.focus = Focus.LIST
        self.state.focus_epoch += 1

    def on_search_focused(self) -> None:
        """搜索框获得焦点：记录焦点态，并消费「唤回全选」一次性标记。

        标记在非可观测的服务容器上，消费它不触发重绘，因此不会打断正在进行的
        输入法组合。
        """
        if self.state.focus != Focus.SEARCH:
            self.state.focus = Focus.SEARCH
        self._s.select_on_focus = False

    # ------------------------------------------------------------------ 选中集合
    def selected_items(self) -> list[ResultItem]:
        """按索引升序返回当前选中的结果项。"""
        return [
            self.state.results[i]
            for i in sorted(self.state.selected)
            if i < len(self.state.results)
        ]

    def best_result_index(self) -> int:
        """回车默认选中：运行次数最大的结果；全部未运行则选第一个。"""
        best, best_count = 0, 0
        for index, row in enumerate(self.state.results):
            if row.run_count > best_count:
                best, best_count = index, row.run_count
        return best

    def ensure_selected(self, index: int) -> None:
        """右键菜单执行前确保目标行被选中。"""
        if index not in self.state.selected:
            self.state.selected, self.state.anchor = {index}, index

    # ------------------------------------------------------------------ 鼠标
    def on_row_click(self, index: int, col: str | None = None) -> None:
        """行单击：按 Ctrl/Shift 多选，否则单选；双击时间窗内二次点击按列执行动作。"""
        ctrl, shift = self._s.screen.modifier_state()

        if shift and self.state.anchor >= 0:
            lo, hi = sorted((self.state.anchor, index))
            self.state.selected = set(range(lo, hi + 1))
        elif ctrl:
            self.state.selected = self.state.selected ^ {index}  # 整体赋值触发可观测重绘
            self.state.anchor = index
        else:
            self.state.selected, self.state.anchor = {index}, index

        # 鼠标点击同样进入列表焦点态，Delete/Enter/方向键对鼠标选中生效
        self.state.focus = Focus.LIST

        # 修饰键点击只做多选，不参与双击判定（避免 Ctrl 连点误开文件）
        if ctrl or shift:
            self._last_click_index, self._last_click_time = -1, 0.0
            return

        now = time.monotonic()
        if (
            now - self._last_click_time < self._s.screen.double_click_seconds()
            and self._last_click_index == index
        ):
            self._last_click_index, self._last_click_time = -1, 0.0
            self.on_row_double_click(index, col)
        else:
            self._last_click_index, self._last_click_time = index, now

    def on_row_double_click(self, index: int, col: str | None) -> None:
        """双击动作：路径列打开所在文件夹，其余列打开条目本身。"""
        if not (0 <= index < len(self.state.results)):
            return
        if col == "path":
            asyncio.create_task(self._ctx.actions.open_folder(index))
            return
        # 双击前单击已完成选中；多选状态下沿用批量打开的既有语义
        if index not in self.state.selected:
            self.state.selected, self.state.anchor = {index}, index
        asyncio.create_task(self._ctx.actions.open_selected())

    # ------------------------------------------------------------------ 键盘
    def move_selection(self, delta: int) -> None:
        """键盘 ↑/↓ 移动选中，并让选中行保持可见。"""
        if not self.state.results:
            return
        current = max(self.state.selected) if self.state.selected else -1
        nxt = max(0, min(current + delta, len(self.state.results) - 1))
        self.state.selected, self.state.anchor = {nxt}, nxt
        asyncio.create_task(self._ctx.search.scroll_results(row=nxt))
