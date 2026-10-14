"""键盘视图模型：页面级快捷键分发（搜索框 / 结果列表两种焦点域）。

事件已在 infra 层归一化为 ``KeyStroke``，本层不感知任何 UI 框架细节。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from csearch.models.entities import KeyStroke
from csearch.models.enums import Focus

if TYPE_CHECKING:
    from csearch.viewmodel.context import AppContext


class KeyboardViewModel:
    """页面级快捷键路由。"""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self.state = ctx.state

    async def handle(self, stroke: KeyStroke) -> None:
        key, ctrl = stroke.key, stroke.ctrl
        state = self.state
        selection, search, actions, menu = (
            self._ctx.selection,
            self._ctx.search,
            self._ctx.actions,
            self._ctx.menu,
        )

        match (ctrl, key):
            case (False, "f5"):
                await search.run_search(keep_selection=True)
            case (True, "d"):
                await actions.copy_paths()
            case (True, "e"):
                await actions.reveal_selected()
            case (True, "a"):
                state.selected, state.anchor = set(range(len(state.results))), 0
            case (False, "escape") if state.menu_kind is not None:
                menu.close()  # 右键菜单优先被 Esc 关掉，避免误清空搜索框
            case (False, "escape") if state.focus == Focus.LIST:
                selection.focus_search()
            case (False, "escape"):
                # 与清空输入框一致：同步清空结果，避免书签/结果切换时重挂载旧列表造成首键卡顿
                search.set_query("", run=False)
                selection.focus_search()
            case (False, "arrowdown") if state.focus == Focus.SEARCH and state.results:
                state.selected, state.anchor = {0}, 0
                selection.focus_list()
            case (False, "arrowdown") if state.focus == Focus.LIST:
                selection.move_selection(1)
            case (False, "arrowup") if state.focus == Focus.LIST:
                selection.move_selection(-1)
            case (False, "enter") if state.focus == Focus.LIST:
                await actions.open_selected()
            case (False, "delete") if state.focus == Focus.LIST:
                await actions.delete_selected()
            case (False, "pageup") if state.focus == Focus.LIST:
                await search.scroll_results(-500)
            case (False, "pagedown") if state.focus == Focus.LIST:
                await search.scroll_results(500)
            case (False, "home") if state.focus == Focus.LIST:
                await search.scroll_results(row=0)
            case (False, "end") if state.focus == Focus.LIST:
                await search.scroll_results(row=max(0, len(state.results) - 1))
