"""顶部搜索行：搜索框 + 分类/时间/大小筛选 + 书签保存 + 刷新 + 热键设置。"""

from __future__ import annotations

import asyncio

import flet as ft

from csearch import logic
from csearch.state import AppState
from csearch.types import CATEGORIES, SIZE_RANGES, TIME_RANGES


def _dropdown(state: AppState, field: str, value: str, options: list[tuple[str, str]], width: int) -> ft.Control:
    return ft.Dropdown(
        value=value,
        width=width,
        dense=True,
        text_size=12,
        options=[ft.DropdownOption(key=k, text=v) for k, v in options],
        on_select=lambda e: logic.on_filter(state, field, e.control.value),
        tooltip={"category": "文件分类", "time": "修改时间", "size": "文件大小"}[field],
    )


@ft.component
def SearchBar(state: AppState):
    async def _submit() -> None:
        if state.results:
            if not state.selected:
                state.selected, state.anchor = {0}, 0
            await logic.open_selected(state)

    return ft.Container(
        padding=ft.Padding(12, 8, 12, 8),
        bgcolor="#FFFFFF",
        border=ft.Border(bottom=ft.BorderSide(1, "#E4E7ED")),
        content=ft.Row(
            spacing=8,
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
                    ignore_up_down_keys=True,
                    autofocus=state.focus == "search",
                    key=f"search-{state.focus_epoch}" if state.focus == "search" else "search",
                    on_change=lambda e: logic.on_query_changed(state, e.control.value),
                    on_submit=lambda e: asyncio.create_task(_submit()),
                    on_focus=lambda e: setattr(state, "focus", "search"),
                ),
                _dropdown(state, "category", state.category, CATEGORIES, 96),
                _dropdown(state, "time", state.time_range, TIME_RANGES, 92),
                _dropdown(state, "size", state.size_range, SIZE_RANGES, 110),
                ft.IconButton(
                    ft.Icons.BOOKMARK_ADD,
                    icon_size=20,
                    tooltip="保存当前搜索条件为书签",
                    on_click=lambda e: logic.open_bookmark(state),
                ),
                ft.IconButton(
                    ft.Icons.REFRESH,
                    icon_size=20,
                    tooltip="刷新 (F5)",
                    on_click=lambda e: asyncio.create_task(logic.run_search(state, keep_selection=True)),
                ),
                ft.IconButton(
                    ft.Icons.SETTINGS,
                    icon_size=20,
                    tooltip="设置全局热键",
                    on_click=lambda e: logic.open_hotkey(state),
                ),
            ],
        ),
    )
