"""右键菜单覆盖层：打开 / 关闭与指针坐标换算。

Flet 1.0.0 桌面客户端不渲染 ``ft.ContextMenu``（原生 secondary_items 与程序化
``open()`` 都没有任何可见效果），因此菜单改为根 Stack 自绘覆盖层，本模块只负责
「作用对象 + 页面逻辑坐标」这两件事，不涉及任何控件构造。

坐标约定：``TapEvent.global_position`` 是**页面内容逻辑坐标**（bootstrap 已把
``page.padding`` 设为 0，故与根 Stack 的 left/top 同处一个坐标系），直接可用。
"""

from __future__ import annotations

from csearch.constants import Focus, MenuKind
from csearch.controller.common import page
from csearch.controller.selection import ensure_selected
from csearch.models import Bookmark
from csearch.state import AppState

# 菜单面板尺寸（与 ui/menu.py 对齐，仅用于贴边夹紧）
MENU_WIDTH = 220
ROW_ITEM_COUNT = 7      # 结果行菜单项数
BOOKMARK_ITEM_COUNT = 2  # 书签菜单项数
ITEM_HEIGHT = 30
PANEL_PADDING = 8


def _pointer(e) -> tuple[float, float]:
    """从事件里取指针坐标（页面逻辑像素）。"""
    gp = getattr(e, "global_position", None)
    x = getattr(gp, "x", None)
    if x is not None:
        return float(x), float(getattr(gp, "y", 0.0) or 0.0)
    # 兜底：少数事件只带 global_x / global_y
    return float(getattr(e, "global_x", 0.0) or 0.0), float(
        getattr(e, "global_y", 0.0) or 0.0
    )


def _clamp(x: float, y: float, item_count: int) -> tuple[float, float]:
    """菜单贴近右/下边缘时拉回可视区。"""
    height = item_count * ITEM_HEIGHT + PANEL_PADDING
    try:
        width = float(page().width or 0.0)
        page_height = float(page().height or 0.0)
    except Exception:  # noqa: BLE001
        return x, y
    if width and x + MENU_WIDTH > width:
        x = max(0.0, width - MENU_WIDTH)
    if page_height and y + height > page_height:
        y = max(0.0, page_height - height)
    return x, y


def open_row_menu(state: AppState, index: int, e) -> None:
    """结果行右键：先选中目标行（多选时保留整组），再在指针处弹出菜单。"""
    ensure_selected(state, index)
    state.focus = Focus.LIST
    state.menu_kind = MenuKind.RESULT_ROW
    state.menu_row = index
    state.menu_x, state.menu_y = _clamp(*_pointer(e), item_count=ROW_ITEM_COUNT)


def open_bookmark_menu(state: AppState, bookmark: Bookmark, e) -> None:
    """书签卡片右键 / 更多按钮：在指针处弹出菜单。"""
    state.menu_kind = MenuKind.BOOKMARK
    state.menu_bookmark = bookmark.id
    state.menu_x, state.menu_y = _clamp(*_pointer(e), item_count=BOOKMARK_ITEM_COUNT)


def close_menu(state: AppState) -> None:
    """关闭菜单并清空目标。"""
    state.menu_kind = None
    state.menu_row = -1
    state.menu_bookmark = ""
