"""顶部搜索行：搜索框 + 分类/时间/大小筛选 + 书签保存 + 刷新 + 热键设置。"""

from __future__ import annotations

import asyncio

import flet as ft

from csearch import logic
from csearch.state import AppState, services
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
        # 回车两步走：第一次仅选中「运行次数最大」的结果（无运行记录则选第一个），
        # 再次回车打开选中结果；若已有选中（鼠标点击等）则直接打开。
        if not state.query.strip():
            return
        # 回车优先：取消仍在防抖等待中的搜索任务，避免其与回车搜索竞争
        # 导致结果被 seq 守卫丢弃（回车后拿不到结果）
        if services._debounce is not None:
            services._debounce.cancel()
            services._debounce = None
        # 防抖未触发 / 搜索进行中时，先按当前条件落库查询，保证选中基于最新结果
        current = services.engine.build_query(state.query, state.category, state.time_range, state.size_range)
        if state.searching or not state.results or state.last_query != current:
            await logic.run_search(state)
        if not state.results:
            return
        if state.focus == "list":
            return  # 列表焦点下回车由页面级键盘事件处理（避免重复打开）
        if not state.selected:
            best = logic.best_result_index(state)
            state.selected, state.anchor = {best}, best
            logic.focus_list(state)
            asyncio.create_task(logic.scroll_results(state, None, row=best))
            return
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
                    on_focus=lambda e: setattr(state, "focus", "search") if state.focus != "search" else None,
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
