"""书签面板：搜索框为空时展示，卡片网格，单击应用、更多菜单重命名/删除。

卡片用「描边 + 悬停底色」而不是阴影：一屏十几张卡时阴影会糊成一片，
描边在明暗两种主题下都能干净地界定边界。
"""

from __future__ import annotations

import ui

from csearch.models.constants import CATEGORIES, SIZE_RANGES, TIME_RANGES
from csearch.models.entities import Bookmark
from csearch.view.events import pointer_position
from csearch.view.theme import (
    ACCENT,
    BORDER,
    FS,
    FW,
    HINT,
    HOVER,
    ICON,
    RAD,
    SP,
    SURFACE,
    TEXT,
    TEXT_SUB,
    radius_all,
    sym_padding,
)
from csearch.viewmodel.context import AppContext

_CATEGORY_LABEL = dict(CATEGORIES)
_TIME_LABEL = dict(TIME_RANGES)
_SIZE_LABEL = dict(SIZE_RANGES)


def _summary(bookmark: Bookmark) -> str:
    """书签条件摘要（一行）。"""
    parts = [f"「{bookmark.query}」" if bookmark.query else "全部文件"]
    if bookmark.category != "all":
        parts.append(_CATEGORY_LABEL.get(bookmark.category, bookmark.category))
    if bookmark.time_range != "any":
        parts.append(_TIME_LABEL.get(bookmark.time_range, bookmark.time_range))
    if bookmark.size_range != "any":
        parts.append(_SIZE_LABEL.get(bookmark.size_range, bookmark.size_range))
    return " · ".join(parts)


@ui.component
def _bookmark_card(ctx: AppContext, bookmark: Bookmark):
    hovered, set_hovered = ui.use_state(False)

    def _open_menu(e) -> None:
        ctx.menu.open_bookmark(bookmark, *pointer_position(e))

    return ui.GestureDetector(
        mouse_cursor=ui.MouseCursor.CLICK,
        on_tap=lambda e: ctx.bookmarks.apply(bookmark),
        on_secondary_tap_down=_open_menu,
        content=ui.Container(
            border=ui.Border.all(1, BORDER if not hovered else ACCENT),
            border_radius=radius_all(RAD["lg"]),
            bgcolor=HOVER if hovered else SURFACE,
            padding=ui.Padding(SP["3"], SP["2"], SP["2"], SP["2"]),
            on_hover=lambda e: set_hovered(e.data == "true"),
            content=ui.Column(
                spacing=SP["1"],
                tight=True,
                controls=[
                    ui.Row(
                        spacing=SP["2"],
                        vertical_alignment=ui.CrossAxisAlignment.CENTER,
                        controls=[
                            ui.Icon(ui.Icons.BOOKMARK, size=ICON["md"], color=ACCENT),
                            ui.Text(
                                bookmark.name,
                                size=FS["body"],
                                weight=FW["semibold"],
                                color=TEXT,
                                expand=True,
                                no_wrap=True,
                                overflow=ui.TextOverflow.ELLIPSIS,
                            ),
                            # 用 GestureDetector 而非 IconButton：需要点击坐标来定位
                            # 覆盖层菜单（IconButton 的 on_click 不携带坐标）
                            ui.GestureDetector(
                                mouse_cursor=ui.MouseCursor.CLICK,
                                on_tap=_open_menu,
                                content=ui.Container(
                                    padding=sym_padding(SP["1"], SP["1"]),
                                    border_radius=radius_all(RAD["sm"]),
                                    tooltip="重命名 / 删除",
                                    content=ui.Icon(
                                        ui.Icons.MORE_HORIZ, size=ICON["md"], color=TEXT_SUB
                                    ),
                                ),
                            ),
                        ],
                    ),
                    ui.Text(
                        _summary(bookmark),
                        size=FS["caption"],
                        color=TEXT_SUB,
                        max_lines=1,
                        overflow=ui.TextOverflow.ELLIPSIS,
                    ),
                ],
            ),
        ),
    )


@ui.component
def BookmarksPanel(ctx: AppContext):
    bookmarks = ctx.state.bookmarks
    if not bookmarks:
        # 空态交给 cs-ui 的 empty_block：图标底座 / 主文 / 下一步提示三段结构与
        # 框架其它地方完全一致，不再每个面板各画一套间距。
        return ui.Container(
            expand=True,
            bgcolor=SURFACE,
            alignment=ui.Alignment(0, 0),
            content=ui.empty_block(
                "暂无书签",
                hint="设置好搜索条件后，点顶部书签图标即可保存",
                icon=ui.Icons.BOOKMARK_BORDER,
            ),
        )

    return ui.Container(
        expand=True,
        bgcolor=SURFACE,
        padding=ui.Padding(SP["4"], SP["3"], SP["4"], SP["2"]),
        content=ui.Column(
            spacing=SP["2"],
            controls=[
                ui.Row(
                    spacing=SP["2"],
                    vertical_alignment=ui.CrossAxisAlignment.CENTER,
                    controls=[
                        ui.Text(
                            "我的书签",
                            size=FS["body"],
                            weight=FW["semibold"],
                            color=TEXT_SUB,
                        ),
                        ui.Text(
                            str(len(bookmarks)),
                            size=FS["caption"],
                            color=HINT,
                        ),
                    ],
                ),
                ui.GridView(
                    expand=True,
                    max_extent=260,
                    child_aspect_ratio=3.6,
                    spacing=SP["2"],
                    run_spacing=SP["2"],
                    controls=[_bookmark_card(ctx, bm) for bm in bookmarks],
                ),
            ],
        ),
    )
