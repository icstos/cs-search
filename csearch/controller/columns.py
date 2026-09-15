"""结果列宽：表头分隔条拖拽（双通道）+ 窗口缩放时弹性列自适应。

双通道说明：GestureDetector 水平拖拽事件在部分客户端数据不可靠（delta 常为
None），因此同时保留「手势事件」与「按下后 GetCursorPos 轮询」两条路径，任一
可用即可拖拽；表头每帧跟手，行控件按快照 60ms 节流重排以保证流畅。
"""

from __future__ import annotations

import asyncio
from typing import Any

from csearch.constants import DEFAULT_COL_WIDTHS, MAX_COL_WIDTH, MIN_COL_WIDTHS
from csearch.controller.common import page
from csearch.platform import cursor_x, dpi_scale, mouse_down
from csearch.state import AppState

# 手势通道的起始状态（轮询通道用局部变量）
_drag_start = 0
_drag_origin: float | None = None


# --------------------------------------------------------------------- 手势通道
def start_col_drag_gesture(state: AppState, col: str, e: Any) -> None:
    """GestureDetector 拖拽开始：记录起始宽度与指针全局位置。"""
    global _drag_start, _drag_origin
    if state.drag_col is not None:
        return
    state.drag_col = col
    _drag_start = state.col_widths.get(col, DEFAULT_COL_WIDTHS.get(col, 100))
    _drag_origin = getattr(getattr(e, "global_position", None), "dx", None)


def update_col_drag_gesture(state: AppState, col: str, e: Any) -> None:
    """拖拽中：按指针位移（逻辑像素）更新列宽。"""
    if state.drag_col != col or _drag_origin is None:
        return
    gx = getattr(getattr(e, "global_position", None), "dx", None)
    if gx is None:
        return
    width = max(
        MIN_COL_WIDTHS.get(col, 60),
        min(int(_drag_start + gx - _drag_origin), MAX_COL_WIDTH),
    )
    if width != state.col_widths.get(col):
        state.col_widths = {**state.col_widths, col: width}


def end_col_drag_gesture(state: AppState) -> None:
    state.drag_col = None


# --------------------------------------------------------------------- 轮询通道
async def start_col_drag(state: AppState, col: str) -> None:
    """按下分隔条后轮询鼠标位置，松开左键结束（与 UI 框架无关，稳定可用）。"""
    if state.drag_col is not None:
        return
    state.drag_col = col
    state.row_width_snap = dict(state.col_widths)
    start_x = cursor_x()
    start_w = state.col_widths.get(col, DEFAULT_COL_WIDTHS.get(col, 100))
    logical_width = page().window.width
    scale = dpi_scale(logical_width)
    frame = 0
    try:
        while mouse_down():
            width = max(
                MIN_COL_WIDTHS.get(col, 60),
                min(int(start_w + (cursor_x() - start_x) / scale), MAX_COL_WIDTH),
            )
            if abs(width - state.col_widths.get(col, 100)) >= 1:  # 1px 灵敏度防抖
                state.col_widths = {**state.col_widths, col: width}
            frame += 1
            if frame % 5 == 0:
                # 节流：行控件每 ~60ms 重排一次（表头每帧跟手）
                state.row_width_snap = dict(state.col_widths)
            await asyncio.sleep(0.012)
    finally:
        state.row_width_snap = dict(state.col_widths)  # 松手后行对齐最终宽度
        state.drag_col = None


def adapt_columns(state: AppState) -> None:
    """窗口缩放时按比例适配弹性列（名称/路径），固定列（大小/时间/次数）不变。"""
    try:
        total = float(page().window.width or 1040)
        fixed = (
            state.col_widths.get("size", DEFAULT_COL_WIDTHS["size"])
            + state.col_widths.get("mtime", DEFAULT_COL_WIDTHS["mtime"])
            + state.col_widths.get("run_count", DEFAULT_COL_WIDTHS["run_count"])
            + 40
        )
        flexible = max(240.0, total - fixed)
        base = (
            state.col_widths.get("name", DEFAULT_COL_WIDTHS["name"])
            + state.col_widths.get("path", DEFAULT_COL_WIDTHS["path"])
        )
        ratio = flexible / base
        name = max(MIN_COL_WIDTHS["name"],
                   int(state.col_widths.get("name", DEFAULT_COL_WIDTHS["name"]) * ratio))
        path = max(MIN_COL_WIDTHS["path"],
                   int(state.col_widths.get("path", DEFAULT_COL_WIDTHS["path"]) * ratio))
        if (name, path) != (state.col_widths.get("name"), state.col_widths.get("path")):
            state.col_widths = {**state.col_widths, "name": name, "path": path}
    except Exception:  # noqa: BLE001
        pass
