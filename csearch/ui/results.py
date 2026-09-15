"""结果列表：表头（可拖拽列宽 / 点击排序）+ 虚拟 ListView + 右键菜单 + 空态。"""

from __future__ import annotations

import asyncio

import flet as ft

from csearch.constants import COLUMNS, DEFAULT_COL_WIDTHS, ROW_HEIGHT
from csearch.controller import (
    copy_names,
    copy_paths,
    delete_selected,
    end_col_drag_gesture,
    ensure_selected,
    launch_everything,
    load_more,
    no_more_to_load,
    on_row_click,
    on_sort,
    open_folder,
    open_selected,
    request_run_count,
    reveal_selected,
    start_col_drag,
    start_col_drag_gesture,
    update_col_drag_gesture,
)
from csearch.models import ResultItem
from csearch.state import AppState, services
from csearch.ui.bookmarks import BookmarksPanel
from csearch.ui.icons import icon_for
from csearch.ui.theme import ALIGNMENT, TEXT_ALIGN, C, sym_padding

# 结果 ListView 引用（controller 程序化滚动用），组件注册
services.results_list = ft.Ref[ft.ListView]()


# --------------------------------------------------------------------- 单行
@ft.component
def _result_row(state: AppState, item: ResultItem, index: int):
    # 依赖变化才重建：切换选中 / 列宽快照变化（拖拽时低频更新）
    selected = index in state.selected
    widths = state.row_width_snap or state.col_widths
    _, set_w = ft.use_state(0)
    ft.use_memo(
        lambda: set_w(lambda w: w + 1),
        [selected, tuple(sorted(widths.items()))],
    )

    def _cells() -> list[ft.Control]:
        cells: list[ft.Control] = []
        for col, _title, align in COLUMNS:
            width = widths.get(col, DEFAULT_COL_WIDTHS.get(col, 100))
            if col == "name":
                icon_name, icon_color = icon_for(item.name, item.is_folder)
                content = ft.Row(
                    spacing=6,
                    controls=[
                        ft.Icon(icon_name, size=16, color=icon_color),
                        ft.Text(
                            item.name, size=13,
                            color=C.ON_PRIMARY if selected else C.TEXT,
                            no_wrap=True, expand=True,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                )
            elif col == "path":
                content = ft.Text(
                    item.path, size=12, color=C.TEXT_SUB, no_wrap=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                )
            elif col == "size":
                content = ft.Text(item.size_str, size=12, color=C.TEXT_SUB,
                                  text_align=TEXT_ALIGN[align], no_wrap=True)
            elif col == "mtime":
                content = ft.Text(item.date_str, size=12, color=C.TEXT_SUB,
                                  text_align=TEXT_ALIGN[align], no_wrap=True)
            else:  # run_count
                content = ft.Text(
                    str(item.run_count) if item.run_count else "",
                    size=12,
                    color=C.SUCCESS if item.run_count else C.TEXT_FAINT,
                    weight=ft.FontWeight.W_600 if item.run_count else ft.FontWeight.W_400,
                    text_align=TEXT_ALIGN[align], no_wrap=True,
                )
            cells.append(
                ft.Container(
                    width=width,
                    padding=sym_padding(8, 6),
                    alignment=ALIGNMENT[align],
                    content=content,
                )
            )
        return cells

    return ft.GestureDetector(
        mouse_cursor=ft.MouseCursor.CLICK,
        on_tap=lambda e: on_row_click(state, index),
        on_secondary_tap_down=lambda e: asyncio.create_task(
            _build_context_menu(state, index, e)
        ),
        content=ft.Container(
            height=ROW_HEIGHT,
            bgcolor=C.PRIMARY_CONTAINER if selected else (
                C.SURFACE_ALT if index % 2 else C.SURFACE
            ),
            content=ft.Row(spacing=0, controls=_cells()),
        ),
    )


async def _build_context_menu(state: AppState, index: int, e) -> None:
    """行右键：先确保目标行选中，再在指针处弹出菜单。"""
    ensure_selected(state, index)
    services.menu_row = index
    menu = ft.ContextMenu(
        [
            ft.MenuItemButton(
                content=ft.Text("打开 (Enter)"),
                on_click=lambda _: asyncio.create_task(open_selected(state)),
            ),
            ft.MenuItemButton(
                content=ft.Text("打开所在文件夹 (Ctrl+E)"),
                on_click=lambda _: asyncio.create_task(reveal_selected(state)),
            ),
            ft.MenuItemButton(
                content=ft.Text("打开文件夹（双击路径列）"),
                on_click=lambda _: asyncio.create_task(
                    open_folder(state, services.menu_row)
                ),
            ),
            ft.MenuItemButton(
                content=ft.Text("复制完整路径 (Ctrl+D)"),
                on_click=lambda _: asyncio.create_task(copy_paths(state)),
            ),
            ft.MenuItemButton(
                content=ft.Text("复制文件名"),
                on_click=lambda _: asyncio.create_task(copy_names(state)),
            ),
            ft.MenuItemButton(
                content=ft.Text("设置运行次数…"),
                on_click=lambda _: request_run_count(state, services.menu_row),
            ),
            ft.MenuItemButton(
                content=ft.Text("删除到回收站 (Delete)"),
                on_click=lambda _: asyncio.create_task(delete_selected(state)),
            ),
        ]
    )
    try:
        await menu.open(x=e.global_x, y=e.global_y)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------- 表头
def _header_cell(state: AppState, col: str, title: str, width: int) -> ft.Control:
    active = state.sort_col == col
    arrow = ""
    if active:
        arrow = " ▲" if not state.sort_desc else " ▼"
    return ft.GestureDetector(
        on_tap=lambda e: on_sort(state, col),
        mouse_cursor=ft.MouseCursor.CLICK,
        content=ft.Container(
            width=width,
            padding=sym_padding(8, 6),
            content=ft.Text(
                f"{title}{arrow}", size=12,
                weight=ft.FontWeight.W_600,
                color=C.PRIMARY if active else C.TEXT_SUB,
                no_wrap=True,
            ),
        ),
    )


def _separator(state: AppState, col: str) -> ft.Control:
    """列分隔条：外层水平拖拽手势 + 内层按下轮询（双通道兜底）。"""
    active = state.drag_col == col or state.hover_col == col
    bar = ft.Container(
        width=10,
        content=ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=2,
                    expand=True,
                    bgcolor=C.TEXT_HINT if active else C.DIVIDER,
                )
            ],
        ),
    )
    inner = ft.GestureDetector(
        content=bar,
        mouse_cursor=ft.MouseCursor.RESIZE_COLUMN,
        on_tap_down=lambda e: asyncio.create_task(start_col_drag(state, col)),
    )
    return ft.GestureDetector(
        content=inner,
        on_horizontal_drag_start=lambda e: start_col_drag_gesture(state, col, e),
        on_horizontal_drag_update=lambda e: update_col_drag_gesture(state, col, e),
        on_horizontal_drag_end=lambda e: end_col_drag_gesture(state),
        on_hover=lambda e: setattr(state, "hover_col", col if e.data == "true" else None),
    )


def _table_header(state: AppState) -> ft.Control:
    cells: list[ft.Control] = []
    for col, title, _align in COLUMNS:
        width = state.col_widths.get(col, DEFAULT_COL_WIDTHS.get(col, 100))
        cells.append(_header_cell(state, col, title, width))
        cells.append(_separator(state, col))
    total = sum(
        state.col_widths.get(c, DEFAULT_COL_WIDTHS.get(c, 100))
        for c, _, _ in COLUMNS
    )
    return ft.Container(
        height=32,
        bgcolor=C.HEADER_BG,
        border=ft.Border(
            top=ft.BorderSide(1, C.BORDER), bottom=ft.BorderSide(1, C.BORDER)
        ),
        content=ft.Row(
            spacing=0,
            width=total + 40,
            controls=cells,
        ),
    )


# --------------------------------------------------------------------- 空态
def _engine_down_card(state: AppState) -> ft.Control:
    return ft.Container(
        expand=True,
        alignment=ft.Alignment(0, 0),
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
            controls=[
                ft.Icon(ft.Icons.ERROR_OUTLINE, size=48, color=C.DANGER),
                ft.Text("Everything 服务未运行", size=16, weight=ft.FontWeight.W_600),
                ft.Text(state.engine_msg or "请启动 Everything 后使用",
                        size=13, color=C.TEXT_SUB),
                ft.FilledButton(
                    "一键启动 Everything",
                    icon=ft.Icons.PLAY_ARROW,
                    on_click=lambda e: launch_everything(),
                ),
            ],
        ),
    )


def _empty_hint() -> ft.Control:
    return ft.Container(
        expand=True,
        alignment=ft.Alignment(0, 0),
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
            controls=[
                ft.Icon(ft.Icons.SEARCH_OFF, size=48, color=C.TEXT_HINT),
                ft.Text("无匹配结果", size=14, color=C.TEXT_HINT),
            ],
        ),
    )


# --------------------------------------------------------------------- 列表
@ft.component
def Results(state: AppState):
    def _on_scroll_event(e) -> None:
        pixels = float(e.pixels or 0)
        max_ext = float(e.max_scroll_extent or 0)
        # 持续同步真实滚动位置，滚轮桥据此做绝对偏移
        services.wheel_acc = pixels
        state.max_ext = max_ext
        viewport = float(e.viewport_dimension or 0)
        # 接近底部自动加载下一页（硬边界处不再触发，避免越界弹动）
        if (
            max_ext > 0
            and not no_more_to_load(state)
            and pixels + viewport >= max_ext - 120
        ):
            asyncio.create_task(load_more(state))

    if not state.engine_ok:
        return _engine_down_card(state)

    # 搜索框为空：展示书签面板（同时保留空 results，不挂载 ListView，避免旧列表残留）
    if not state.query.strip():
        return BookmarksPanel(state)

    rows = [
        _result_row(state, item, i)
        for i, item in enumerate(state.results)
    ]
    list_view = ft.ListView(
        ref=services.results_list,
        controls=rows,
        spacing=0,
        padding=ft.Padding(0, 4, 0, 4),
        on_scroll=_on_scroll_event,
    )

    return ft.Column(
        expand=True,
        spacing=0,
        controls=[
            _table_header(state),
            ft.Container(
                expand=True,
                bgcolor=C.SURFACE,
                content=ft.Stack(
                    expand=True,
                    controls=[
                        ft.Scrollbar(expand=True, content=list_view),
                        ft.ProgressRing(
                            width=20, height=20, stroke_width=2,
                            visible=state.searching,
                            left=12, top=8,
                        ),
                        (
                            _empty_hint()
                            if not state.searching and not state.results
                            else ft.Container()
                        ),
                    ],
                ),
            ),
        ],
    )
