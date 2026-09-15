"""controller 公共工具：当前页、轻提示、选中项与焦点切换。"""

from __future__ import annotations

import flet as ft

from csearch.constants import Focus
from csearch.models import ResultItem
from csearch.state import AppState


def page() -> ft.Page:
    """当前组件上下文中的 Page（声明式组件内调用安全）。"""
    return ft.context.page


def snack(text: str) -> None:
    """轻量 SnackBar 提示（失败静默，不影响主流程）。"""
    try:
        page().show_dialog(ft.SnackBar(ft.Text(text, size=13), duration=1800))
    except Exception:  # noqa: BLE001
        pass


def selected_items(state: AppState) -> list[ResultItem]:
    """按索引升序返回当前选中的结果项。"""
    return [state.results[i] for i in sorted(state.selected) if i < len(state.results)]


def focus_search(state: AppState) -> None:
    """把键盘焦点切回搜索框（focus_epoch+1 触发 key 重挂载以实现 autofocus）。"""
    state.focus, state.focus_epoch = Focus.SEARCH, state.focus_epoch + 1


def focus_list(state: AppState) -> None:
    """把键盘焦点切到结果列表。"""
    state.focus, state.focus_epoch = Focus.LIST, state.focus_epoch + 1
