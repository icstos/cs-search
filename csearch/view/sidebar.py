"""左侧导航栏组件（保留备用：当前主界面采用单列布局，未挂载本组件）。"""

from __future__ import annotations

import asyncio

import flet as ft

from csearch.view.theme import C, sym_padding
from csearch.viewmodel.context import AppContext


def _nav_item(icon: str, label: str, active: bool, on_click) -> ft.Control:
    return ft.Container(
        border_radius=8,
        padding=sym_padding(8, 6),
        bgcolor=C.PRIMARY_CONTAINER if active else None,
        content=ft.Row(
            spacing=10,
            controls=[
                ft.Icon(
                    icon, size=18,
                    color=C.PRIMARY if active else C.TEXT_SUB,
                ),
                ft.Text(
                    label, size=13,
                    weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_400,
                    color=C.PRIMARY if active else C.TEXT_STRONG,
                ),
            ],
        ),
        on_click=on_click,
        ink=True,
    )


def _section_label(text: str) -> ft.Control:
    return ft.Container(
        padding=ft.Padding(8, 6, 8, 2),
        content=ft.Text(text, size=11, color=C.TEXT_HINT,
                        weight=ft.FontWeight.W_600),
    )


@ft.component
def Sidebar(ctx: AppContext):
    state = ctx.state
    return ft.Container(
        width=200,
        bgcolor=C.SIDEBAR_BG,
        border=ft.Border(right=ft.BorderSide(1, C.BORDER)),
        padding=ft.Padding(8, 12, 8, 12),
        content=ft.Column(
            spacing=2,
            controls=[
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.SPEED, color=C.PRIMARY, size=22),
                        ft.Text("CSearch", size=16, weight=ft.FontWeight.W_700),
                    ],
                ),
                ft.Container(height=8),
                _section_label("排序"),
                _nav_item(
                    ft.Icons.SORT_BY_ALPHA, "按名称", state.sort_col == "name",
                    lambda e: ctx.search.on_sort("name"),
                ),
                _nav_item(
                    ft.Icons.FOLDER_OUTLINED, "按路径", state.sort_col == "path",
                    lambda e: ctx.search.on_sort("path"),
                ),
                _nav_item(
                    ft.Icons.SD_STORAGE, "按大小", state.sort_col == "size",
                    lambda e: ctx.search.on_sort("size"),
                ),
                _nav_item(
                    ft.Icons.ACCESS_TIME, "按时间", state.sort_col == "mtime",
                    lambda e: ctx.search.on_sort("mtime"),
                ),
                ft.Container(height=8),
                _section_label("筛选"),
                _nav_item(
                    ft.Icons.FOLDER_SPECIAL, "仅文件夹",
                    state.category == "folder",
                    lambda e: ctx.search.on_filter(
                        "category", "all" if state.category == "folder" else "folder"
                    ),
                ),
                ft.Container(expand=True),
                _nav_item(
                    ft.Icons.BOOKMARK_ADD, "保存书签", False,
                    lambda e: ctx.bookmarks.open_save_dialog(),
                ),
                _nav_item(
                    ft.Icons.KEYBOARD, "全局热键", False,
                    lambda e: ctx.settings.open_hotkey(),
                ),
                _nav_item(
                    ft.Icons.MINIMIZE, "最小化到托盘", False,
                    lambda e: asyncio.create_task(ctx.window.toggle()),
                ),
                _nav_item(
                    ft.Icons.POWER_SETTINGS_NEW, "退出", False,
                    lambda e: asyncio.create_task(ctx.window.quit()),
                ),
                ft.Container(height=4),
                ft.Text("↑↓ 选择 · Enter 打开", size=10, color=C.TEXT_FAINT),
            ],
        ),
    )
