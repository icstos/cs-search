"""左侧导航栏组件（保留备用：当前主界面采用单列布局，未挂载本组件）。"""

from __future__ import annotations

import asyncio

import ui

from csearch.view.theme import C, sym_padding
from csearch.viewmodel.context import AppContext


def _nav_item(icon: str, label: str, active: bool, on_click) -> ui.Control:
    return ui.Container(
        border_radius=8,
        padding=sym_padding(8, 6),
        bgcolor=C.PRIMARY_CONTAINER if active else None,
        content=ui.Row(
            spacing=10,
            controls=[
                ui.Icon(
                    icon, size=18,
                    color=C.PRIMARY if active else C.TEXT_SUB,
                ),
                ui.Text(
                    label, size=13,
                    weight=ui.FontWeight.W_600 if active else ui.FontWeight.W_400,
                    color=C.PRIMARY if active else C.TEXT_STRONG,
                ),
            ],
        ),
        on_click=on_click,
        ink=True,
    )


def _section_label(text: str) -> ui.Control:
    return ui.Container(
        padding=ui.Padding(8, 6, 8, 2),
        content=ui.Text(text, size=11, color=C.TEXT_HINT,
                        weight=ui.FontWeight.W_600),
    )


@ui.component
def Sidebar(ctx: AppContext):
    state = ctx.state
    return ui.Container(
        width=200,
        bgcolor=C.SIDEBAR_BG,
        border=ui.Border(right=ui.BorderSide(1, C.BORDER)),
        padding=ui.Padding(8, 12, 8, 12),
        content=ui.Column(
            spacing=2,
            controls=[
                ui.Row(
                    spacing=8,
                    controls=[
                        ui.Icon(ui.Icons.SPEED, color=C.PRIMARY, size=22),
                        ui.Text("CSearch", size=16, weight=ui.FontWeight.W_700),
                    ],
                ),
                ui.Container(height=8),
                _section_label("排序"),
                _nav_item(
                    ui.Icons.SORT_BY_ALPHA, "按名称", state.sort_col == "name",
                    lambda e: ctx.search.on_sort("name"),
                ),
                _nav_item(
                    ui.Icons.FOLDER_OUTLINED, "按路径", state.sort_col == "path",
                    lambda e: ctx.search.on_sort("path"),
                ),
                _nav_item(
                    ui.Icons.SD_STORAGE, "按大小", state.sort_col == "size",
                    lambda e: ctx.search.on_sort("size"),
                ),
                _nav_item(
                    ui.Icons.ACCESS_TIME, "按时间", state.sort_col == "mtime",
                    lambda e: ctx.search.on_sort("mtime"),
                ),
                ui.Container(height=8),
                _section_label("筛选"),
                _nav_item(
                    ui.Icons.FOLDER_SPECIAL, "仅文件夹",
                    state.category == "folder",
                    lambda e: ctx.search.on_filter(
                        "category", "all" if state.category == "folder" else "folder"
                    ),
                ),
                ui.Container(expand=True),
                _nav_item(
                    ui.Icons.BOOKMARK_ADD, "保存书签", False,
                    lambda e: ctx.bookmarks.open_save_dialog(),
                ),
                _nav_item(
                    ui.Icons.KEYBOARD, "全局热键", False,
                    lambda e: ctx.settings.open_hotkey(),
                ),
                _nav_item(
                    ui.Icons.MINIMIZE, "最小化到托盘", False,
                    lambda e: asyncio.create_task(ctx.window.toggle()),
                ),
                _nav_item(
                    ui.Icons.POWER_SETTINGS_NEW, "退出", False,
                    lambda e: asyncio.create_task(ctx.window.quit()),
                ),
                ui.Container(height=4),
                ui.Text("↑↓ 选择 · Enter 打开", size=10, color=C.TEXT_FAINT),
            ],
        ),
    )
