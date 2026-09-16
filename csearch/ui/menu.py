"""自绘右键菜单覆盖层（根 Stack 的最后一层）。

为什么不用 ``ft.ContextMenu``：Flet 1.0.0 桌面客户端对它没有任何渲染效果
（原生 ``secondary_items`` 与程序化 ``open()`` 都不可见，实测 ``on_dismiss``
会立刻以 ``btn=secondary`` 触发），所以这里用「全屏透明遮罩 + 绝对定位面板」自绘，
行为完全可控。

实测要点（改动前请先读）：
- 覆盖层必须放在 ``ft.Stack(fit=ft.StackFit.EXPAND)`` 里，否则没设宽度的子控件
  会在松约束下收缩；
- 遮罩用 ``left/top/right/bottom=0`` 铺满，``bgcolor`` 即使是全透明也会参与命中
  测试，点击别处即关闭菜单；
- 菜单项**必须显式给宽度**：Column 的子控件在交叉轴上按内容收缩，只给高度的项
  实际可点区域只有文字那么宽，点菜单空白处会完全没反应。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import flet as ft

from csearch.constants import MenuKind
from csearch.controller import (
    close_menu,
    copy_names,
    copy_paths,
    delete_bookmark,
    delete_selected,
    open_folder,
    open_selected,
    rename_bookmark,
    request_run_count,
    reveal_selected,
)
from csearch.state import AppState
from csearch.ui.theme import C, radius_all, sym_padding

MENU_WIDTH = 220
ITEM_HEIGHT = 30
_PANEL_PADDING = 4
_ITEM_WIDTH = MENU_WIDTH - _PANEL_PADDING * 2


@ft.component
def _MenuItem(
    label: str,
    on_select: Callable[[], None],
    hint: str = "",
    danger: bool = False,
) -> ft.Control:
    """单条菜单项（hover 高亮 + 点击分发）。"""
    hover, set_hover = ft.use_state(False)
    trailing: list[ft.Control] = (
        [ft.Text(hint, size=11, color=C.TEXT_HINT, no_wrap=True)] if hint else []
    )
    return ft.Container(
        width=_ITEM_WIDTH,
        height=ITEM_HEIGHT,
        padding=sym_padding(12, 0),
        border_radius=radius_all(4),
        bgcolor=C.PRIMARY_CONTAINER if hover else None,
        on_click=lambda e: on_select(),
        on_hover=lambda e: set_hover(e.data == "true"),
        content=ft.Row(
            spacing=8,
            controls=[
                ft.Text(
                    label,
                    size=13,
                    color=C.DANGER if danger else C.TEXT,
                    expand=True,
                    no_wrap=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                *trailing,
            ],
        ),
    )


# --------------------------------------------------------------------- 结果行菜单
def _action(state: AppState, fn: Callable[[], None]) -> Callable[[], None]:
    """包装菜单项动作：先关掉覆盖层，再执行动作。

    必须关，否则是「右键只能用一次」的经典坑：遮罩是全屏且可命中的，菜单一直挂着
    就等于在整张列表上盖了一层透明板，之后所有点击（含下一次右键）都落在遮罩上，
    行手势再也收不到。
    """
    def run() -> None:
        close_menu(state)
        fn()

    return run


def _result_items(state: AppState) -> list[ft.Control]:
    """结果行菜单项：动作在点击瞬间读取 state.menu_row 对应的目标行。"""
    index = state.menu_row

    def open_item() -> None:
        asyncio.create_task(open_selected(state))

    def reveal_item() -> None:
        asyncio.create_task(reveal_selected(state))

    def folder_item() -> None:
        asyncio.create_task(open_folder(state, index))

    def copy_path_item() -> None:
        asyncio.create_task(copy_paths(state))

    def copy_name_item() -> None:
        asyncio.create_task(copy_names(state))

    def run_count_item() -> None:
        request_run_count(state, index)

    def delete_item() -> None:
        asyncio.create_task(delete_selected(state))

    return [
        _MenuItem("打开", _action(state, open_item), "Enter"),
        _MenuItem("打开所在文件夹", _action(state, reveal_item), "Ctrl+E"),
        _MenuItem("打开文件夹", _action(state, folder_item), "双击路径列"),
        _MenuItem("复制完整路径", _action(state, copy_path_item), "Ctrl+D"),
        _MenuItem("复制文件名", _action(state, copy_name_item)),
        _MenuItem("设置运行次数…", _action(state, run_count_item)),
        _MenuItem("删除到回收站", _action(state, delete_item), "Delete", danger=True),
    ]


# --------------------------------------------------------------------- 书签菜单
def _bookmark_items(state: AppState) -> list[ft.Control]:
    bookmark = next(
        (bm for bm in state.bookmarks if bm.id == state.menu_bookmark), None
    )
    if bookmark is None:
        return []

    def rename_item() -> None:
        rename_bookmark(state, bookmark)

    def delete_item() -> None:
        delete_bookmark(state, bookmark)

    return [
        _MenuItem("重命名", _action(state, rename_item)),
        _MenuItem("删除", _action(state, delete_item), danger=True),
    ]


# --------------------------------------------------------------------- 覆盖层
def _panel(state: AppState, items: list[ft.Control]) -> ft.Control:
    """菜单面板：按指针坐标绝对定位。"""
    return ft.Container(
        left=state.menu_x,
        top=state.menu_y,
        width=MENU_WIDTH,
        bgcolor=C.SURFACE,
        border=ft.Border.all(1, C.BORDER_STRONG),
        border_radius=radius_all(6),
        padding=ft.Padding(
            _PANEL_PADDING, _PANEL_PADDING, _PANEL_PADDING, _PANEL_PADDING
        ),
        content=ft.Column(spacing=0, tight=True, controls=items),
    )


def menu_layer(state: AppState) -> list[ft.Control]:
    """右键菜单覆盖层控件列表（未打开时返回空列表，直接展开进根 Stack）。"""
    if state.menu_kind is None:
        return []
    items = (
        _result_items(state)
        if state.menu_kind is MenuKind.RESULT_ROW
        else _bookmark_items(state)
    )
    if not items:
        return []
    return [
        ft.Container(  # 遮罩：点击别处关闭
            left=0,
            top=0,
            right=0,
            bottom=0,
            bgcolor=ft.Colors.TRANSPARENT,
            on_click=lambda e: close_menu(state),
        ),
        _panel(state, items),
    ]
