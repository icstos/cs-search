"""顶部搜索栏：搜索框（防抖触发）+ 刷新 + 热键设置入口。"""

from __future__ import annotations

import asyncio

import flet as ft

from csearch import controller
from csearch.state import AppState


@ft.component
def SearchBar(state: AppState):
    page = ft.context.page

    async def _on_submit():
        # 搜索框 Enter：打开选中项（无选中则第一行）
        if state.results:
            if not state.selected:
                state.selected = {0}
            await controller.open_selected(page, state)

    return ft.Container(
        padding=ft.Padding(12, 8, 12, 8),
        bgcolor="#FFFFFF",
        border=ft.Border(bottom=ft.BorderSide(1, "#E4E7ED")),
        content=ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.SEARCH, color="#5F6368", size=20),
                ft.TextField(
                    value=state.query,
                    hint_text="搜索文件名，支持 Everything 语法（ext: / content: / 正则…）",
                    expand=True,
                    dense=True,
                    border=ft.InputBorder.NONE,
                    text_size=14,
                    cursor_color="#1A73E8",
                    ignore_up_down_keys=True,  # ↓ 键上浮到页面级键盘处理（跳转列表）
                    autofocus=state.focus_target == "search",
                    key=f"search-{state.focus_epoch}" if state.focus_target == "search" else "search",
                    on_change=lambda e: controller.on_query_changed(state, page, e.control.value),
                    on_submit=lambda e: asyncio.create_task(_on_submit()),
                    on_focus=lambda e: setattr(state, "focus_target", "search"),
                ),
                ft.IconButton(
                    ft.Icons.REFRESH,
                    icon_size=20,
                    tooltip="刷新 (F5)",
                    on_click=lambda e: asyncio.create_task(
                        controller.run_search(state, page, reset=False, keep_selection=True)
                    ),
                ),
                ft.IconButton(
                    ft.Icons.SETTINGS,
                    icon_size=20,
                    tooltip="设置全局热键",
                    on_click=lambda e: controller.open_hotkey_dialog(state),
                ),
            ],
        ),
    )
