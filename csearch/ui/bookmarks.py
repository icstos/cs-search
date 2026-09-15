"""书签面板：搜索框为空时展示，卡片网格，单击应用、更多菜单重命名/删除。"""

from __future__ import annotations

import asyncio

import flet as ft

from csearch.constants import CATEGORIES, SIZE_RANGES, TIME_RANGES
from csearch.controller import apply_bookmark, delete_bookmark, rename_bookmark
from csearch.models import Bookmark
from csearch.state import AppState
from csearch.ui.theme import C, radius_all, sym_padding

_CATEGORY_LABEL = dict(CATEGORIES)
_TIME_LABEL = dict(TIME_RANGES)
_SIZE_LABEL = dict(SIZE_RANGES)


def _summary(bm: Bookmark) -> str:
    """书签条件摘要（一行）。"""
    parts = [f"关键词「{bm.query}」" if bm.query else "全部文件"]
    if bm.category != "all":
        parts.append(_CATEGORY_LABEL.get(bm.category, bm.category))
    if bm.time_range != "any":
        parts.append(_TIME_LABEL.get(bm.time_range, bm.time_range))
    if bm.size_range != "any":
        parts.append(_SIZE_LABEL.get(bm.size_range, bm.size_range))
    return " · ".join(parts)


async def _card_menu(state: AppState, bm: Bookmark, e) -> None:
    menu = ft.ContextMenu(
        [
            ft.MenuItemButton(
                content=ft.Text("重命名"),
                on_click=lambda _: rename_bookmark(state, bm),
            ),
            ft.MenuItemButton(
                content=ft.Text("删除"),
                on_click=lambda _: delete_bookmark(state, bm),
            ),
        ]
    )
    try:
        await menu.open(x=e.global_x, y=e.global_y)
    except Exception:  # noqa: BLE001
        pass


@ft.component
def _bookmark_card(state: AppState, bm: Bookmark):
    return ft.GestureDetector(
        mouse_cursor=ft.MouseCursor.CLICK,
        on_tap=lambda e: apply_bookmark(state, bm),
        on_secondary_tap_down=lambda e: asyncio.create_task(_card_menu(state, bm, e)),
        content=ft.Container(
            border=ft.Border.all(1, C.BORDER),
            border_radius=radius_all(8),
            bgcolor=C.SURFACE,
            padding=ft.Padding(12, 10, 6, 10),
            content=ft.Column(
                spacing=4,
                tight=True,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.BOOKMARK, size=16, color=C.WARNING),
                            ft.Text(
                                bm.name, size=13, weight=ft.FontWeight.W_600,
                                color=C.TEXT, expand=True, no_wrap=True,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.IconButton(
                                ft.Icons.MORE_HORIZ,
                                icon_size=16,
                                padding=2,
                                tooltip="重命名 / 删除",
                                on_click=lambda e: asyncio.create_task(
                                    _card_menu(state, bm, e)
                                ),
                            ),
                        ],
                    ),
                    ft.Text(
                        _summary(bm), size=11, color=C.TEXT_SUB,
                        max_lines=2, overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
            ),
        ),
    )


@ft.component
def BookmarksPanel(state: AppState):
    if not state.bookmarks:
        return ft.Container(
            expand=True,
            alignment=ft.Alignment(0, 0),
            content=ft.Column(
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
                controls=[
                    ft.Icon(ft.Icons.BOOKMARK_BORDER, size=48, color=C.TEXT_FAINT),
                    ft.Text("暂无书签", size=14, color=C.TEXT_HINT),
                    ft.Text(
                        "设置搜索条件后，点击顶部 ★ 保存为书签",
                        size=12, color=C.TEXT_HINT,
                    ),
                ],
            ),
        )

    return ft.Container(
        expand=True,
        padding=sym_padding(12, 12),
        content=ft.Column(
            spacing=8,
            controls=[
                ft.Text("我的书签", size=13, weight=ft.FontWeight.W_600,
                        color=C.TEXT_SUB),
                ft.GridView(
                    expand=True,
                    max_extent=240,
                    child_aspect_ratio=3.2,
                    spacing=8,
                    run_spacing=8,
                    controls=[_bookmark_card(state, bm) for bm in state.bookmarks],
                ),
            ],
        ),
    )
