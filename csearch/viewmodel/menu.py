"""右键菜单视图模型：打开 / 关闭与坐标夹紧。

Flet 1.0.3 桌面客户端不渲染 ``ft.ContextMenu``（原生 secondary_items 与程序化
``open()`` 都没有任何可见效果），因此菜单改为根 Stack 自绘覆盖层，本层只负责
「作用对象 + 页面逻辑坐标」这两件事，不涉及任何控件构造。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from csearch.models.constants import (
    MENU_BOOKMARK_ITEM_COUNT,
    MENU_CLAMP_PADDING,
    MENU_ITEM_HEIGHT,
    MENU_ROW_ITEM_COUNT,
    MENU_WIDTH,
)
from csearch.models.entities import Bookmark
from csearch.models.enums import Focus, MenuKind

if TYPE_CHECKING:
    from csearch.viewmodel.context import AppContext


class MenuViewModel:
    """自绘覆盖层菜单的状态管理。"""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._s = ctx.services
        self.state = ctx.state

    # ------------------------------------------------------------------ 坐标
    def _clamp(self, x: float, y: float, item_count: int) -> tuple[float, float]:
        """菜单贴近右/下边缘时拉回可视区。"""
        height = item_count * MENU_ITEM_HEIGHT + MENU_CLAMP_PADDING
        try:
            width, page_height = self._s.window.viewport_size()
        except Exception:  # noqa: BLE001
            return x, y
        if width and x + MENU_WIDTH > width:
            x = max(0.0, width - MENU_WIDTH)
        if page_height and y + height > page_height:
            y = max(0.0, page_height - height)
        return x, y

    # ------------------------------------------------------------------ 打开 / 关闭
    def open_row(self, index: int, x: float, y: float) -> None:
        """结果行右键：先选中目标行（多选时保留整组），再在指针处弹出菜单。"""
        self._ctx.selection.ensure_selected(index)
        self.state.focus = Focus.LIST
        self.state.menu_kind = MenuKind.RESULT_ROW
        self.state.menu_row = index
        self.state.menu_x, self.state.menu_y = self._clamp(
            x, y, MENU_ROW_ITEM_COUNT
        )

    def open_bookmark(self, bookmark: Bookmark, x: float, y: float) -> None:
        """书签卡片右键 / 更多按钮：在指针处弹出菜单。"""
        self.state.menu_kind = MenuKind.BOOKMARK
        self.state.menu_bookmark = bookmark.id
        self.state.menu_x, self.state.menu_y = self._clamp(
            x, y, MENU_BOOKMARK_ITEM_COUNT
        )

    def close(self) -> None:
        """关闭菜单并清空目标。"""
        self.state.menu_kind = None
        self.state.menu_row = -1
        self.state.menu_bookmark = ""
