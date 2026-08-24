"""结果列表：可排序表头 + 交替行背景 + 类型图标 + 右键菜单 + 懒加载滚动 + 键盘导航。

性能关键点：
- 行控件构建结果用 use_memo 缓存（依赖 results/selected），输入关键词重绘时零重建；
- ListView build_controls_on_demand=True，客户端只物化可见行；
- 滚动增量加载（scroll_delta 累计 > 阈值触发），首批 200 条。
"""

from __future__ import annotations

import asyncio

import flet as ft

from csearch import controller
from csearch.icons import icon_for
from csearch.state import AppState, ResultItem

_BORDER = "#E4E7ED"
_HEADER_BG = "#F1F3F4"
_ROW_H = 30  # 紧凑行高，单屏更多结果

_COLUMNS = [
    ("name", "名称", 2),
    ("path", "路径", 3),
    ("size", "大小", 1),
    ("mtime", "修改时间", 1),
]


@ft.component
def ResultsView(state: AppState):
    page = ft.context.page
    scroll_acc = ft.use_ref(0.0)  # 滚动增量累加器（不触发重绘）

    # 行控件缓存：仅结果集/选中集变化时重建
    rows = ft.use_memo(
        lambda: [_row(state, page, i, item) for i, item in enumerate(state.results)],
        [state.results, state.selected],
    )

    def _on_scroll(e):
        d = getattr(e, "scroll_delta", None)
        dy = float(getattr(d, "y", 0) or 0)
        if dy > 0:
            acc = scroll_acc.current + dy
            scroll_acc.current = acc
            if acc > 350:
                scroll_acc.current = 0.0
                asyncio.create_task(controller.load_more(state, page))

    def _on_list_key(e):
        key = getattr(e, "key", "") or ""
        asyncio.create_task(controller.on_list_key(state, page, key))

    if not state.results and not state.searching:
        body: ft.Control = ft.Container(
            expand=True,
            alignment=ft.Alignment(0, 0),
            content=ft.Text(
                state.engine_msg if not state.engine_ok else (
                    "没有匹配的结果" if state.query or state.category != "all"
                    else "输入关键词开始搜索"
                ),
                size=13,
                color="#9AA0A6",
            ),
        )
    else:
        body = ft.KeyboardListener(
            expand=True,
            key=f"kl-{state.focus_epoch}" if state.focus_target == "list" else "kl",
            autofocus=state.focus_target == "list",
            on_key_down=_on_list_key,
            content=ft.ListView(
                controls=rows,
                expand=True,
                spacing=0,
                padding=ft.Padding(0, 4, 0, 4),
                build_controls_on_demand=True,
                on_scroll=_on_scroll,
            ),
        )

    return ft.Column(
        expand=True,
        spacing=0,
        controls=[
            _header(state, page),
            body,
        ],
    )


# ------------------------------------------------------------------ 表头
def _header(state: AppState, page: ft.Page) -> ft.Control:
    cells = []
    for key, label, flex in _COLUMNS:
        if key == "name":
            cells.append(_header_cell(state, page, key, label, expand=flex))
        elif key == "path":
            cells.append(_header_cell(state, page, key, label, expand=flex))
        elif key == "size":
            cells.append(_header_cell(state, page, key, label, width=86, align_right=True))
        else:
            cells.append(_header_cell(state, page, key, label, width=130))
    return ft.Container(
        bgcolor=_HEADER_BG,
        padding=ft.Padding(8, 6, 8, 6),
        border=ft.Border(bottom=ft.BorderSide(1, _BORDER)),
        content=ft.Row(spacing=0, controls=cells),
    )


def _header_cell(
    state: AppState,
    page: ft.Page,
    key: str,
    label: str,
    expand=None,
    width=None,
    align_right: bool = False,
) -> ft.Control:
    active = state.sort_col == key
    icon = ft.Icons.ARROW_DOWNWARD if state.sort_desc else ft.Icons.ARROW_UPWARD
    row = ft.Row(
        spacing=2,
        alignment=ft.MainAxisAlignment.END if align_right else ft.MainAxisAlignment.START,
        controls=[
            ft.Text(label, size=12, weight=ft.FontWeight.W_600,
                    color="#1A73E8" if active else "#5F6368"),
            ft.Icon(icon, size=13, color="#1A73E8") if active else ft.Container(width=0, height=0),
        ],
    )
    kw = {"expand": expand} if expand else {"width": width}
    return ft.Container(
        **kw,
        on_click=lambda e: controller.on_sort(state, page, key),
        content=row,
    )


# ------------------------------------------------------------------ 行
def _row(state: AppState, page: ft.Page, i: int, item: ResultItem) -> ft.Control:
    selected = i in state.selected
    bg = "#E8F0FE" if selected else ("#FFFFFF" if i % 2 == 0 else "#F6F8FA")
    icon_name, icon_color = icon_for(item.name, item.is_folder)

    def act(fn):
        def _h(e):
            controller.ensure_selected(state, i)
            asyncio.create_task(fn(page, state))

        return _h

    menu_items = [
        ft.PopupMenuItem(content="打开", icon=ft.Icons.OPEN_IN_NEW, on_click=act(controller.open_selected)),
        ft.PopupMenuItem(content="打开文件所在位置", icon=ft.Icons.FOLDER_OPEN, on_click=act(controller.reveal_selected)),
        ft.PopupMenuItem(content="复制完整路径", icon=ft.Icons.CONTENT_COPY, on_click=act(controller.copy_paths)),
        ft.PopupMenuItem(content="复制文件名", icon=ft.Icons.CONTENT_PASTE, on_click=act(controller.copy_names)),
        ft.PopupMenuItem(),
        ft.PopupMenuItem(content="删除到回收站", icon=ft.Icons.DELETE_OUTLINE, on_click=act(lambda p, s: controller.request_delete(s))),
        ft.PopupMenuItem(content="永久删除", icon=ft.Icons.DELETE_FOREVER, on_click=act(lambda p, s: controller.request_delete(s))),
    ]

    name_text = ft.Text(
        item.name, size=13, expand=True,
        weight=ft.FontWeight.W_500 if selected else None,
        color="#202124" if not selected else "#174EA6",
        overflow=ft.TextOverflow.ELLIPSIS, max_lines=1,
    )
    path_text = ft.Text(
        item.path, size=12, expand=True, color="#5F6368",
        overflow=ft.TextOverflow.ELLIPSIS, max_lines=1,
    )
    size_text = ft.Text(item.size_str, size=12, color="#5F6368", width=86,
                        text_align=ft.TextAlign.RIGHT)
    date_text = ft.Text(item.date_str, size=12, color="#5F6368", width=130)

    return ft.ContextMenu(
        secondary_items=menu_items,
        content=ft.Container(
            height=_ROW_H,
            bgcolor=bg,
            padding=ft.Padding(8, 0, 8, 0),
            on_click=lambda e, idx=i: controller.on_row_click(state, page, idx),
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(icon_name, size=15, color=icon_color),
                    name_text,
                    path_text,
                    size_text,
                    date_text,
                ],
            ),
        ),
    )
