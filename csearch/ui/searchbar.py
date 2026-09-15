"""顶部搜索行：搜索框 + 分类/时间/大小筛选 + 正则开关 + 书签/刷新/热键。"""

from __future__ import annotations

import asyncio

import flet as ft

from csearch.constants import CATEGORIES, SIZE_RANGES, TIME_RANGES, Focus
from csearch.controller import (
    on_filter,
    on_query_changed,
    open_bookmark,
    open_hotkey,
    run_search,
    submit,
    toggle_regex,
)
from csearch.state import AppState, services
from csearch.ui.theme import C, bottom_border, sym_padding

_TOOLTIPS = {"category": "文件分类", "time": "修改时间", "size": "文件大小"}


def _regex_toggle(state: AppState) -> ft.Control:
    """正则开关胶囊：高亮表示已开启。"""
    on = state.use_regex
    return ft.TextButton(
        content=".*",
        tooltip=(
            "正则搜索：已开启，点击关闭（按正则匹配文件名）"
            if on
            else r"正则搜索：点击开启（参考 Everything，如 ^report.*\.xlsx$）"
        ),
        style=ft.ButtonStyle(
            color=C.PRIMARY if on else C.TEXT_SUB,
            bgcolor=C.PRIMARY_CONTAINER if on else C.HEADER_BG,
            padding=ft.Padding(10, 2, 10, 2),
            shape=ft.StadiumBorder(),
            side=ft.BorderSide(1, C.PRIMARY if on else C.BORDER_STRONG),
            text_style=ft.TextStyle(
                size=12,
                weight=ft.FontWeight.W_600 if on else ft.FontWeight.W_500,
            ),
        ),
        on_click=lambda e: toggle_regex(state),
    )


def _dropdown(state: AppState, field_name: str, value: str,
              options: list[tuple[str, str]], width: int) -> ft.Control:
    return ft.Dropdown(
        value=value,
        width=width,
        dense=True,
        text_size=12,
        options=[ft.DropdownOption(key=k, text=v) for k, v in options],
        on_select=lambda e: on_filter(state, field_name, e.control.value),
        tooltip=_TOOLTIPS[field_name],
    )


@ft.component
def SearchBar(state: AppState):
    def _on_search_focus(e) -> None:
        # 获得焦点时记录焦点态，并消费「唤回全选」一次性标记（标记在非可观测的
        # services 上，消费不触发重绘，当前挂载的 selection 保持不变）
        if state.focus != Focus.SEARCH:
            state.focus = Focus.SEARCH
        services.select_on_focus = False

    return ft.Container(
        padding=sym_padding(12, 8),
        bgcolor=C.SURFACE,
        border=bottom_border(),
        content=ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.SEARCH, color=C.TEXT_SUB, size=20),
                ft.TextField(
                    value=state.query,
                    hint_text=(
                        r"正则模式：输入正则表达式匹配文件名，如 ^report.*\.xlsx$"
                        if state.use_regex
                        else "搜索文件名，支持 Everything 语法（ext: / content: / 正则…）"
                    ),
                    expand=True,
                    dense=True,
                    # 单个 NoInputBorder 对默认/聚焦/悬停全部状态生效，保持扁平无描边
                    border=ft.NoInputBorder(),
                    text_size=14,
                    ignore_up_down_keys=True,
                    autofocus=state.focus == Focus.SEARCH,
                    # 唤回窗口时全选已有内容（一次性，输入即可覆盖旧查询）
                    selection=(
                        ft.TextSelection(base_offset=0, extent_offset=len(state.query))
                        if services.select_on_focus and state.query
                        else None
                    ),
                    key=f"search-{state.focus_epoch}" if state.focus == Focus.SEARCH else "search",
                    on_change=lambda e: on_query_changed(state, e.control.value),
                    on_submit=lambda e: asyncio.create_task(submit(state)),
                    on_focus=_on_search_focus,
                ),
                _regex_toggle(state),
                _dropdown(state, "category", state.category, CATEGORIES, 96),
                _dropdown(state, "time", state.time_range, TIME_RANGES, 92),
                _dropdown(state, "size", state.size_range, SIZE_RANGES, 110),
                ft.IconButton(
                    ft.Icons.BOOKMARK_ADD, icon_size=20,
                    tooltip="保存当前搜索条件为书签",
                    on_click=lambda e: open_bookmark(state),
                ),
                ft.IconButton(
                    ft.Icons.REFRESH, icon_size=20,
                    tooltip="刷新 (F5)",
                    on_click=lambda e: asyncio.create_task(
                        run_search(state, keep_selection=True)
                    ),
                ),
                ft.IconButton(
                    ft.Icons.SETTINGS, icon_size=20,
                    tooltip="设置全局热键",
                    on_click=lambda e: open_hotkey(state),
                ),
            ],
        ),
    )
