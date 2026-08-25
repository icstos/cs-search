"""书签面板：搜索框无内容时展示于结果区，卡片式，点击一键应用。"""

from __future__ import annotations

import flet as ft

from csearch import logic
from csearch.state import AppState
from csearch.types import CATEGORIES, SIZE_RANGES, TIME_RANGES

_CAT, _TIME, _SIZE = dict(CATEGORIES), dict(TIME_RANGES), dict(SIZE_RANGES)


def _summary(bm) -> str:
    # 仅展示非默认筛选，避免"不限 · 不限"冗余
    parts = [
        bm.query or "全部文件",
        _CAT.get(bm.category, "") if bm.category != "all" else "",
        _TIME.get(bm.time_range, "") if bm.time_range != "any" else "",
        _SIZE.get(bm.size_range, "") if bm.size_range != "any" else "",
    ]
    return " · ".join(p for p in parts if p)


def _card(state: AppState, bm) -> ft.Control:
    return ft.Container(
        border_radius=ft.BorderRadius(10, 10, 10, 10),
        bgcolor="#FFFFFF",
        border=ft.Border.all(1, "#E4E7ED"),
        padding=ft.Padding(12, 10, 6, 10),
        on_click=lambda e: logic.apply_bookmark(state, bm),
        content=ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.BOOKMARK, color="#F9AB00", size=18),
                ft.Column(
                    expand=True,
                    spacing=2,
                    controls=[
                        ft.Text(bm.name, size=13, weight=ft.FontWeight.W_600,
                                color="#202124", overflow=ft.TextOverflow.ELLIPSIS, max_lines=1),
                        ft.Text(_summary(bm), size=11, color="#5F6368",
                                overflow=ft.TextOverflow.ELLIPSIS, max_lines=1),
                    ],
                ),
                ft.PopupMenuButton(
                    icon=ft.Icons.MORE_VERT,
                    icon_size=16,
                    icon_color="#9AA0A6",
                    items=[
                        ft.PopupMenuItem(content="重命名", icon=ft.Icons.EDIT,
                                         on_click=lambda e: logic.rename_bookmark(state, bm)),
                        ft.PopupMenuItem(content="删除", icon=ft.Icons.DELETE_OUTLINE,
                                         on_click=lambda e: logic.delete_bookmark(state, bm)),
                    ],
                ),
            ],
        ),
    )


@ft.component
def BookmarksPanel(state: AppState):
    if not state.bookmarks:
        return ft.Container(
            expand=True,
            alignment=ft.Alignment(0, 0),
            content=ft.Column(
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.BOOKMARK_BORDER, size=36, color="#BDC1C6"),
                    ft.Text("还没有书签", size=14, color="#9AA0A6"),
                    ft.Text("输入关键词搜索后，点击搜索框右侧的 ☆ 保存当前搜索条件", size=12, color="#BDC1C6"),
                ],
            ),
        )
    return ft.GridView(
        controls=[_card(state, bm) for bm in state.bookmarks],
        expand=True,
        max_extent=260,
        spacing=12,
        run_spacing=12,
        padding=ft.Padding(12, 12, 12, 12),
    )
