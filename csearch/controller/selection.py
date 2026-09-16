"""结果选中：单击 / Ctrl 增减 / Shift 连选 / 双击按列执行动作 / 键盘移动。

双击判定说明：
- 同一个 GestureDetector 上 ``on_tap`` + ``on_double_tap`` 互斥（双击只触发
  ``on_double_tap``，会牺牲单击响应的即时性），因此这里沿用「同一行在系统双击
  时间窗内二次 on_tap」的手动判定，单击选中零延迟；
- 时间窗取 ``user32.GetDoubleClickTime()``（默认 500ms），写死小值会漏判系统认可的
  稍慢双击；
- 按列分发：路径列双击打开所在文件夹（对齐 Everything），其余列双击打开条目本身。
"""

from __future__ import annotations

import asyncio
import time

from csearch.constants import Focus
from csearch.controller.actions import open_folder, open_selected
from csearch.controller.search import scroll_results
from csearch.platform import double_click_seconds, modifier_state
from csearch.state import AppState

# 双击判定：上次点击行与时刻（模块级，跨行控件重建仍然有效）
_last_click_i = -1
_last_click_t = 0.0


def on_row_click(state: AppState, index: int, col: str | None = None) -> None:
    """行单击：按 Ctrl/Shift 多选，否则单选；双击时间窗内二次点击按列执行动作。"""
    global _last_click_i, _last_click_t
    ctrl, shift = modifier_state()

    if shift and state.anchor >= 0:
        lo, hi = sorted((state.anchor, index))
        state.selected = set(range(lo, hi + 1))
    elif ctrl:
        state.selected = state.selected ^ {index}  # 整体赋值触发可观测重绘
        state.anchor = index
    else:
        state.selected, state.anchor = {index}, index

    # 鼠标点击同样进入列表焦点态，Delete/Enter/方向键对鼠标选中生效
    state.focus = Focus.LIST

    # 修饰键点击只做多选，不参与双击判定（避免 Ctrl 连点误开文件）
    if ctrl or shift:
        _last_click_i, _last_click_t = -1, 0.0
        return

    now = time.monotonic()
    if now - _last_click_t < double_click_seconds() and _last_click_i == index:
        _last_click_i, _last_click_t = -1, 0.0
        on_row_double_click(state, index, col)
    else:
        _last_click_i, _last_click_t = index, now


def on_row_double_click(state: AppState, index: int, col: str | None) -> None:
    """双击动作：路径列打开所在文件夹，其余列打开条目本身。"""
    if not (0 <= index < len(state.results)):
        return
    if col == "path":
        asyncio.create_task(open_folder(state, index))
        return
    # 双击前单击已完成选中；多选状态下沿用批量打开的既有语义
    if index not in state.selected:
        state.selected, state.anchor = {index}, index
    asyncio.create_task(open_selected(state))


def ensure_selected(state: AppState, index: int) -> None:
    """右键菜单执行前确保目标行被选中。"""
    if index not in state.selected:
        state.selected, state.anchor = {index}, index


def best_result_index(state: AppState) -> int:
    """回车默认选中：运行次数最大的结果；全部未运行则选第一个。"""
    best, best_count = 0, 0
    for i, row in enumerate(state.results):
        if row.run_count > best_count:
            best, best_count = i, row.run_count
    return best


def move_selection(state: AppState, delta: int) -> None:
    """键盘 ↑/↓ 移动选中，并让选中行保持可见。"""
    if not state.results:
        return
    cur = max(state.selected) if state.selected else -1
    nxt = max(0, min(cur + delta, len(state.results) - 1))
    state.selected, state.anchor = {nxt}, nxt
    asyncio.create_task(scroll_results(state, None, row=nxt))
