"""页面级键盘事件：搜索框/列表焦点下的全套快捷键。"""

from __future__ import annotations

from typing import Any

from csearch.constants import Focus
from csearch.controller.actions import (
    copy_paths,
    delete_selected,
    reveal_selected,
)
from csearch.controller.common import focus_list, focus_search
from csearch.controller.menu import close_menu
from csearch.controller.search import (
    on_query_changed,
    run_search,
    scroll_results,
)
from csearch.controller.selection import move_selection
from csearch.state import AppState


async def on_keyboard(state: AppState | None, e: Any) -> None:
    if state is None:
        return
    # Flet 键名形如 "Arrow Down"/"Page Down"（带空格），去空格并小写归一化
    key = str(getattr(e, "key", "") or "").lower().replace(" ", "")
    ctrl = bool(getattr(e, "ctrl", False))
    match (ctrl, key):
        case (False, "f5"):
            await run_search(state, keep_selection=True)
        case (True, "d"):
            await copy_paths(state)
        case (True, "e"):
            await reveal_selected(state)
        case (True, "a"):
            state.selected, state.anchor = set(range(len(state.results))), 0
        case (False, "escape") if state.menu_kind is not None:
            close_menu(state)  # 右键菜单优先被 Esc 关掉，避免误清空搜索框
        case (False, "escape") if state.focus == Focus.LIST:
            focus_search(state)
        case (False, "escape"):
            # 与清空输入框一致：同步清空结果，避免书签/结果切换时重挂载旧列表造成首键卡顿
            on_query_changed(state, "")
            focus_search(state)
        case (False, "arrowdown") if state.focus == Focus.SEARCH and state.results:
            state.selected, state.anchor = {0}, 0
            focus_list(state)
        case (False, "arrowdown") if state.focus == Focus.LIST:
            move_selection(state, 1)
        case (False, "arrowup") if state.focus == Focus.LIST:
            move_selection(state, -1)
        case (False, "enter") if state.focus == Focus.LIST:
            from csearch.controller.actions import open_selected

            await open_selected(state)
        case (False, "delete") if state.focus == Focus.LIST:
            await delete_selected(state)
        case (False, "pageup") if state.focus == Focus.LIST:
            await scroll_results(state, -500)
        case (False, "pagedown") if state.focus == Focus.LIST:
            await scroll_results(state, 500)
        case (False, "home") if state.focus == Focus.LIST:
            await scroll_results(state, None, row=0)
        case (False, "end") if state.focus == Focus.LIST:
            await scroll_results(state, None, row=max(0, len(state.results) - 1))
