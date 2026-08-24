"""侧边栏：分类过滤器 + 修改时间/大小筛选 + 书签管理（与搜索关键词叠加生效）。"""

from __future__ import annotations

import asyncio

import flet as ft

from csearch import controller
from csearch.icons import CATEGORY_ICONS
from csearch.search_engine import CATEGORIES, SIZE_RANGES, TIME_RANGES
from csearch.state import AppState

_ACTIVE_BG = "#E8F0FE"
_ACTIVE_FG = "#1A73E8"


@ft.component
def Sidebar(state: AppState):
    page = ft.context.page

    return ft.Container(
        width=232,
        bgcolor="#FAFBFC",
        padding=ft.Padding(10, 12, 10, 12),
        border=ft.Border(right=ft.BorderSide(1, "#E4E7ED")),
        content=ft.Column(
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Text("分类", size=11, color="#9AA0A6", weight=ft.FontWeight.W_600),
                ft.Container(height=4),
                *[_category_row(state, page, key, label) for key, label in CATEGORIES],
                ft.Container(height=10),
                ft.Text("修改时间", size=11, color="#9AA0A6", weight=ft.FontWeight.W_600),
                ft.Container(height=4),
                ft.Dropdown(
                    value=state.time_range,
                    dense=True,
                    text_size=13,
                    options=[ft.DropdownOption(key=k, text=t) for k, t in TIME_RANGES],
                    on_select=lambda e: controller.on_time_changed(state, page, e.control.value),
                ),
                ft.Container(height=10),
                ft.Text("文件大小", size=11, color="#9AA0A6", weight=ft.FontWeight.W_600),
                ft.Container(height=4),
                ft.Dropdown(
                    value=state.size_range,
                    dense=True,
                    text_size=13,
                    options=[ft.DropdownOption(key=k, text=t) for k, t in SIZE_RANGES],
                    on_select=lambda e: controller.on_size_changed(state, page, e.control.value),
                ),
                ft.Container(height=12),
                ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("书签", size=11, color="#9AA0A6", weight=ft.FontWeight.W_600, expand=True),
                        ft.IconButton(
                            ft.Icons.BOOKMARK_ADD,
                            icon_size=16,
                            icon_color="#5F6368",
                            tooltip="保存当前搜索条件为书签",
                            on_click=lambda e: controller.open_bookmark_dialog(state),
                        ),
                    ],
                ),
                ft.Container(height=2),
                *[_bookmark_row(state, page, bm) for bm in state.bookmarks],
                ft.Container(height=6),
                ft.Text(
                    "右键结果行可执行打开/定位/复制/删除",
                    size=10,
                    color="#BDC1C6",
                ),
            ],
        ),
    )


def _category_row(state: AppState, page: ft.Page, key: str, label: str) -> ft.Control:
    active = state.category == key
    return ft.Container(
        padding=ft.Padding(8, 6, 8, 6),
        border_radius=ft.BorderRadius(6, 6, 6, 6),
        bgcolor=_ACTIVE_BG if active else None,
        on_click=lambda e: controller.on_category_changed(state, page, key),
        content=ft.Row(
            spacing=8,
            controls=[
                ft.Icon(CATEGORY_ICONS[key], size=16, color=_ACTIVE_FG if active else "#5F6368"),
                ft.Text(label, size=13, color=_ACTIVE_FG if active else "#3C4043",
                        weight=ft.FontWeight.W_500 if active else None),
            ],
        ),
    )


def _bookmark_row(state: AppState, page: ft.Page, bm: dict) -> ft.Control:
    return ft.Container(
        padding=ft.Padding(8, 5, 4, 5),
        border_radius=ft.BorderRadius(6, 6, 6, 6),
        on_click=lambda e: controller.apply_bookmark(page, state, bm),
        content=ft.Row(
            spacing=6,
            controls=[
                ft.Icon(ft.Icons.BOOKMARK_BORDER, size=14, color="#F9AB00"),
                ft.Text(bm.get("name", ""), size=12, color="#3C4043", expand=True,
                        overflow=ft.TextOverflow.ELLIPSIS, max_lines=1),
                ft.PopupMenuButton(
                    icon=ft.Icons.MORE_VERT,
                    icon_size=16,
                    icon_color="#9AA0A6",
                    items=[
                        ft.PopupMenuItem(
                            content="重命名",
                            icon=ft.Icons.EDIT,
                            on_click=lambda e: controller.rename_bookmark(state, bm),
                        ),
                        ft.PopupMenuItem(
                            content="删除",
                            icon=ft.Icons.DELETE_OUTLINE,
                            on_click=lambda e: controller.delete_bookmark(page, state, bm),
                        ),
                    ],
                ),
            ],
        ),
    )
