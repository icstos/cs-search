"""结果选中：单击 / Ctrl 增减 / Shift 连选 / 双击打开 / 键盘移动。"""

from __future__ import annotations

import asyncio
import time

from csearch.controller.actions import open_selected
from csearch.controller.search import scroll_results
from csearch.constants import Focus
from csearch.platform import modifier_state
from csearch.state import AppState

# 双击判定：时间窗（秒）与上次点击行
_DOUBLE_CLICK_GAP = 0.4
_last_click_i = -1
_last_click_t = 0.0


def on_row_click(state: AppState, index: int) -> None:
    """行单击：按 Ctrl/Shift 多选，否则单选；同处 0.4s 内二次点击视为双击打开。"""
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
    now = time.monotonic()
    if now - _last_click_t < _DOUBLE_CLICK_GAP and _last_click_i == index:
        _last_click_t = 0.0
        asyncio.create_task(open_selected(state))
    else:
        _last_click_t, _last_click_i = now, index


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
