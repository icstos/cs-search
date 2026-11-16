"""结果列宽视图模型：表头分隔条拖拽（双通道）+ 窗口缩放时弹性列自适应。

双通道说明：GestureDetector 水平拖拽事件在部分客户端数据不可靠（delta 常为
None），因此同时保留「手势事件」与「按下后 GetCursorPos 轮询」两条路径，任一
可用即可拖拽；表头每帧跟手，行控件按快照 60ms 节流重排以保证流畅。

本层不接触任何控件：指针位移由 view 层从事件中提取后传入。
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from csearch.models.constants import DEFAULT_COL_WIDTHS, MAX_COL_WIDTH, MIN_COL_WIDTHS

if TYPE_CHECKING:
    from csearch.viewmodel.context import AppContext

# 拖拽轮询帧间隔（秒）与「行重排」的时间预算（秒）。
# 行重排是整批重建 + 全量 diff，行数上千时一次能到一两百毫秒；这里用上一帧 sleep
# 的溢出量当作渲染占用的代理指标，超预算就自动降频推快照，避免拖拽把事件循环占满。
_DRAG_FRAME = 0.012
_SNAP_LAG_BUDGET = 0.04


class ColumnsViewModel:
    """列宽拖拽与自适应。"""

    def __init__(self, ctx: AppContext) -> None:
        self._s = ctx.services
        self.state = ctx.state
        # 手势通道的起始状态（轮询通道用局部变量）
        self._drag_start = 0
        self._drag_origin: float | None = None

    # ------------------------------------------------------------------ 悬停
    def set_hover(self, col: str | None) -> None:
        self.state.hover_col = col

    # ------------------------------------------------------------------ 手势通道
    def start_drag_gesture(self, col: str, pointer_dx: float | None) -> None:
        """GestureDetector 拖拽开始：记录起始宽度与指针全局位置。"""
        if self.state.drag_col is not None:
            return
        self.state.drag_col = col
        self._drag_start = self.state.col_widths.get(
            col, DEFAULT_COL_WIDTHS.get(col, 100)
        )
        self._drag_origin = pointer_dx

    def update_drag_gesture(self, col: str, pointer_dx: float | None) -> None:
        """拖拽中：按指针位移（逻辑像素）更新列宽。"""
        if self.state.drag_col != col or self._drag_origin is None or pointer_dx is None:
            return
        width = max(
            MIN_COL_WIDTHS.get(col, 60),
            min(int(self._drag_start + pointer_dx - self._drag_origin), MAX_COL_WIDTH),
        )
        if width != self.state.col_widths.get(col):
            self.state.col_widths = {**self.state.col_widths, col: width}

    def end_drag_gesture(self) -> None:
        self.state.drag_col = None

    # ------------------------------------------------------------------ 轮询通道
    async def start_drag(self, col: str) -> None:
        """按下分隔条后轮询鼠标位置，松开左键结束（与 UI 框架无关，稳定可用）。"""
        if self.state.drag_col is not None:
            return
        self.state.drag_col = col
        self.state.row_width_snap = dict(self.state.col_widths)
        start_x = self._s.screen.cursor_x()
        start_w = self.state.col_widths.get(col, DEFAULT_COL_WIDTHS.get(col, 100))
        scale = self._s.screen.dpi_scale(self._s.window.logical_width())
        frame = 0
        lag = 0.0
        try:
            while self._s.screen.mouse_down():
                width = max(
                    MIN_COL_WIDTHS.get(col, 60),
                    min(int(start_w + (self._s.screen.cursor_x() - start_x) / scale), MAX_COL_WIDTH),
                )
                if abs(width - self.state.col_widths.get(col, 100)) >= 1:  # 1px 灵敏度防抖
                    self.state.col_widths = {**self.state.col_widths, col: width}
                frame += 1
                if frame % 5 == 0 and lag < _SNAP_LAG_BUDGET:
                    # 行控件快照（表头始终每帧跟手，观感不受影响）
                    self.state.row_width_snap = dict(self.state.col_widths)
                t0 = time.perf_counter()
                await asyncio.sleep(_DRAG_FRAME)
                # 溢出量 ≈ 上一帧事件循环被渲染占用的时间；越小说明余量越足
                lag = time.perf_counter() - t0 - _DRAG_FRAME
        finally:
            self.state.row_width_snap = dict(self.state.col_widths)  # 松手后行对齐最终宽度
            self.state.drag_col = None

    # ------------------------------------------------------------------ 自适应
    def adapt(self) -> None:
        """窗口缩放时按比例适配弹性列（名称/路径），固定列（大小/时间/次数）不变。"""
        try:
            total = self._s.window.logical_width()
            widths = self.state.col_widths
            fixed = (
                widths.get("size", DEFAULT_COL_WIDTHS["size"])
                + widths.get("mtime", DEFAULT_COL_WIDTHS["mtime"])
                + widths.get("run_count", DEFAULT_COL_WIDTHS["run_count"])
                + 40
            )
            flexible = max(240.0, total - fixed)
            base = (
                widths.get("name", DEFAULT_COL_WIDTHS["name"])
                + widths.get("path", DEFAULT_COL_WIDTHS["path"])
            )
            ratio = flexible / base
            name = max(
                MIN_COL_WIDTHS["name"],
                int(widths.get("name", DEFAULT_COL_WIDTHS["name"]) * ratio),
            )
            path = max(
                MIN_COL_WIDTHS["path"],
                int(widths.get("path", DEFAULT_COL_WIDTHS["path"]) * ratio),
            )
            if (name, path) != (widths.get("name"), widths.get("path")):
                self.state.col_widths = {**widths, "name": name, "path": path}
        except Exception:  # noqa: BLE001
            pass
