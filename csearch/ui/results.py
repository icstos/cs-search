"""结果列表：可排序表头 + 交替行背景 + 类型图标 + 右键菜单 + 懒加载 + 键盘导航。"""

from __future__ import annotations

import asyncio

import flet as ft

from csearch import logic
from csearch.state import AppState
from csearch.types import ResultItem
from csearch.ui.bookmarks import BookmarksPanel
from csearch.ui.icons import icon_for

_BORDER, _HEADER_BG, _ROW_H = "#E4E7ED", "#F1F3F4", 30
_COLUMNS = [("name", "名称", 2), ("path", "路径", 3), ("size", "大小", 1), ("mtime", "修改时间", 1)]


@ft.component
def Results(state: AppState):
    scroll_acc = ft.use_ref(0.0)

    # 行控件缓存：仅结果集/选中集变化时重建（输入关键词重绘零重建）
    rows = ft.use_memo(
        lambda: [_row(state, i, item) for i, item in enumerate(state.results)],
        [state.results, state.selected],
    )

    def _on_scroll(e) -> None:
        delta = getattr(e, "scroll_delta", None)
        dy = float(getattr(delta, "y", 0) or 0)
        if dy > 0:
            scroll_acc.current += dy
            if scroll_acc.current > 350:
                scroll_acc.current = 0.0
                asyncio.create_task(logic.load_more(state))

    def _on_list_key(e) -> None:
        asyncio.create_task(logic.on_list_key(state, getattr(e, "key", "") or ""))

    if not state.query.strip():
        # 搜索框无内容：不显示搜索结果，结果区展示书签
        body: ft.Control = BookmarksPanel(state)
    elif not state.results and not state.searching:
        body = ft.Container(
            expand=True,
            alignment=ft.Alignment(0, 0),
            content=ft.Text(
                state.engine_msg if not state.engine_ok else "没有匹配的结果",
                size=13,
                color="#9AA0A6",
            ),
        )
    else:
        body = ft.KeyboardListener(
            expand=True,
            key=f"kl-{state.focus_epoch}" if state.focus == "list" else "kl",
            autofocus=state.focus == "list",
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
        controls=[_header(state), body],
    )


def _header(state: AppState) -> ft.Control:
    cells: list[ft.Control] = []
    for key, label, flex in _COLUMNS:
        active = state.sort_col == key
        arrow = ft.Icon(
            ft.Icons.ARROW_DOWNWARD if state.sort_desc else ft.Icons.ARROW_UPWARD,
            size=13, color="#1A73E8",
        ) if active else ft.Container(width=0, height=0)
        row = ft.Row(
            spacing=2,
            alignment=ft.MainAxisAlignment.END if key == "size" else ft.MainAxisAlignment.START,
            controls=[
                ft.Text(label, size=12, weight=ft.FontWeight.W_600,
                        color="#1A73E8" if active else "#5F6368"),
                arrow,
            ],
        )
        cells.append(ft.Container(
            expand=flex if key in ("name", "path") else None,
            width=None if key in ("name", "path") else (86 if key == "size" else 130),
            on_click=lambda e, k=key: logic.on_sort(state, k),
            content=row,
        ))
    return ft.Container(
        bgcolor=_HEADER_BG,
        padding=ft.Padding(8, 6, 8, 6),
        border=ft.Border(bottom=ft.BorderSide(1, _BORDER)),
        content=ft.Row(spacing=0, controls=cells),
    )


def _row(state: AppState, index: int, item: ResultItem) -> ft.Control:
    selected = index in state.selected
    bg = "#E8F0FE" if selected else ("#FFFFFF" if index % 2 == 0 else "#F6F8FA")
    icon, color = icon_for(item.name, item.is_folder)

    def act(fn) -> ft.Control:
        return lambda e: (logic.ensure_selected(state, index),
                          asyncio.create_task(fn(state)))[1]

    menu = [
        ft.PopupMenuItem(content="打开", icon=ft.Icons.OPEN_IN_NEW, on_click=act(logic.open_selected)),
        ft.PopupMenuItem(content="打开文件所在位置", icon=ft.Icons.FOLDER_OPEN, on_click=act(logic.reveal_selected)),
        ft.PopupMenuItem(content="复制完整路径", icon=ft.Icons.CONTENT_COPY, on_click=act(logic.copy_paths)),
        ft.PopupMenuItem(content="复制文件名", icon=ft.Icons.CONTENT_PASTE, on_click=act(logic.copy_names)),
        ft.PopupMenuItem(),
        ft.PopupMenuItem(content="删除到回收站", icon=ft.Icons.DELETE_OUTLINE,
                          on_click=lambda e: logic.request_delete(state)),
        ft.PopupMenuItem(content="永久删除", icon=ft.Icons.DELETE_FOREVER,
                          on_click=lambda e: logic.request_delete(state)),
    ]

    return ft.ContextMenu(
        secondary_items=menu,
        content=ft.Container(
            height=_ROW_H,
            bgcolor=bg,
            padding=ft.Padding(8, 0, 8, 0),
            on_click=lambda e, i=index: logic.on_row_click(state, i),
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(icon, size=15, color=color),
                    ft.Text(item.name, size=13, expand=True,
                            weight=ft.FontWeight.W_500 if selected else None,
                            color="#202124" if not selected else "#174EA6",
                            overflow=ft.TextOverflow.ELLIPSIS, max_lines=1),
                    ft.Text(item.path, size=12, expand=True, color="#5F6368",
                            overflow=ft.TextOverflow.ELLIPSIS, max_lines=1),
                    ft.Text(item.size_str, size=12, color="#5F6368", width=86,
                            text_align=ft.TextAlign.RIGHT),
                    ft.Text(item.date_str, size=12, color="#5F6368", width=130),
                ],
            ),
        ),
    )
