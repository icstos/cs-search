"""书签面板：搜索框为空时展示，卡片网格，单击应用、更多菜单重命名/删除。"""

from __future__ import annotations

import ui

from csearch.models.constants import CATEGORIES, SIZE_RANGES, TIME_RANGES
from csearch.models.entities import Bookmark
from csearch.view.events import pointer_position
from csearch.view.theme import C, radius_all, sym_padding
from csearch.viewmodel.context import AppContext

_CATEGORY_LABEL = dict(CATEGORIES)
_TIME_LABEL = dict(TIME_RANGES)
_SIZE_LABEL = dict(SIZE_RANGES)


def _summary(bookmark: Bookmark) -> str:
    """书签条件摘要（一行）。"""
    parts = [f"关键词「{bookmark.query}」" if bookmark.query else "全部文件"]
    if bookmark.category != "all":
        parts.append(_CATEGORY_LABEL.get(bookmark.category, bookmark.category))
    if bookmark.time_range != "any":
        parts.append(_TIME_LABEL.get(bookmark.time_range, bookmark.time_range))
    if bookmark.size_range != "any":
        parts.append(_SIZE_LABEL.get(bookmark.size_range, bookmark.size_range))
    return " · ".join(parts)


@ui.component
def _bookmark_card(ctx: AppContext, bookmark: Bookmark):
    return ui.GestureDetector(
        mouse_cursor=ui.MouseCursor.CLICK,
        on_tap=lambda e: ctx.bookmarks.apply(bookmark),
        on_secondary_tap_down=lambda e: ctx.menu.open_bookmark(
            bookmark, *pointer_position(e)
        ),
        content=ui.Container(
            border=ui.Border.all(1, C.BORDER),
            border_radius=radius_all(8),
            bgcolor=C.SURFACE,
            padding=ui.Padding(12, 10, 6, 10),
            content=ui.Column(
                spacing=4,
                tight=True,
                controls=[
                    ui.Row(
                        controls=[
                            ui.Icon(ui.Icons.BOOKMARK, size=16, color=C.WARNING),
                            ui.Text(
                                bookmark.name, size=13, weight=ui.FontWeight.W_600,
                                color=C.TEXT, expand=True, no_wrap=True,
                                overflow=ui.TextOverflow.ELLIPSIS,
                            ),
                            # 用 GestureDetector 而非 IconButton：需要点击坐标来定位
                            # 覆盖层菜单（IconButton 的 on_click 不携带坐标）
                            ui.GestureDetector(
                                mouse_cursor=ui.MouseCursor.CLICK,
                                on_tap=lambda e: ctx.menu.open_bookmark(
                                    bookmark, *pointer_position(e)
                                ),
                                content=ui.Container(
                                    padding=ui.Padding(4, 4, 4, 4),
                                    border_radius=radius_all(4),
                                    tooltip="重命名 / 删除",
                                    content=ui.Icon(
                                        ui.Icons.MORE_HORIZ, size=16, color=C.TEXT_SUB
                                    ),
                                ),
                            ),
                        ],
                    ),
                    ui.Text(
                        _summary(bookmark), size=11, color=C.TEXT_SUB,
                        max_lines=2, overflow=ui.TextOverflow.ELLIPSIS,
                    ),
                ],
            ),
        ),
    )


@ui.component
def BookmarksPanel(ctx: AppContext):
    if not ctx.state.bookmarks:
        return ui.Container(
            expand=True,
            alignment=ui.Alignment(0, 0),
            content=ui.Column(
                alignment=ui.MainAxisAlignment.CENTER,
                horizontal_alignment=ui.CrossAxisAlignment.CENTER,
                spacing=8,
                controls=[
                    ui.Icon(ui.Icons.BOOKMARK_BORDER, size=48, color=C.TEXT_FAINT),
                    ui.Text("暂无书签", size=14, color=C.TEXT_HINT),
                    ui.Text(
                        "设置搜索条件后，点击顶部 ★ 保存为书签",
                        size=12, color=C.TEXT_HINT,
                    ),
                ],
            ),
        )

    return ui.Container(
        expand=True,
        padding=sym_padding(12, 12),
        content=ui.Column(
            spacing=8,
            controls=[
                ui.Text("我的书签", size=13, weight=ui.FontWeight.W_600,
                        color=C.TEXT_SUB),
                ui.GridView(
                    expand=True,
                    max_extent=240,
                    child_aspect_ratio=3.2,
                    spacing=8,
                    run_spacing=8,
                    controls=[_bookmark_card(ctx, bm) for bm in ctx.state.bookmarks],
                ),
            ],
        ),
    )
