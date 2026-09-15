"""设置：全局热键、自定义大小区间。"""

from __future__ import annotations

import asyncio

from csearch import store
from csearch.constants import DialogKind
from csearch.controller.common import snack
from csearch.controller.search import run_search
from csearch.state import AppState, services


def open_hotkey(state: AppState) -> None:
    state.hotkey_text, state.dialog = store.load_config().hotkey, DialogKind.HOTKEY


def _set_hotkey(combo: str) -> bool:
    """设置全局热键（托盘未启动时不可用，返回 False 由调用方提示）。"""
    tray = services.tray
    return tray.set_hotkey(combo) if tray is not None else False


def confirm_hotkey(state: AppState) -> None:
    combo = state.hotkey_text.strip().lower()
    if combo:
        if not _set_hotkey(combo):
            snack("热键注册失败，请更换组合（如 alt+space / ctrl+shift+f）")
            return
    else:
        _set_hotkey("")  # 空 = 禁用
    store.save_hotkey(combo)
    state.dialog = None
    snack(f"全局热键已更新：{combo or '（已禁用）'}")


def confirm_size(state: AppState) -> None:
    """确认自定义大小区间（输入单位 MB，转换为字节）。"""
    def to_bytes(text: str) -> int | None:
        text = text.strip()
        if not text:
            return None
        try:
            value = float(text)
            return int(value * 1024 * 1024) if value >= 0 else None
        except ValueError:
            return None

    lo, hi = to_bytes(state.size_min), to_bytes(state.size_max)
    if lo is None and hi is None:
        state.dialog = None
        return
    if lo is not None and hi is not None and lo > hi:
        snack("最小不能大于最大")
        return
    state.size_range = f"custom:{lo or ''},{hi or ''}"
    state.dialog = None
    asyncio.create_task(run_search(state))
