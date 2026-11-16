"""自绘右键菜单覆盖层（根 Stack 的最后一层）。

为什么不用 ``ui.ContextMenu``：Flet 1.0 桌面客户端对它没有任何渲染效果
（原生 ``secondary_items`` 与程序化 ``open()`` 都不可见），所以这里用
「全屏透明遮罩 + 绝对定位面板」自绘，行为完全可控。

实测要点（改动前请先读）：
- 覆盖层必须放在 ``ui.Stack(fit=ui.StackFit.EXPAND)`` 里，否则没设宽度的子控件
  会在松约束下收缩；
- 遮罩用 ``left/top/right/bottom=0`` 铺满，``bgcolor`` 即使是全透明也会参与命中
  测试，点击别处即关闭菜单；
- 菜单项**必须显式给宽度**：Column 的子控件在交叉轴上按内容收缩，只给高度的项
  实际可点区域只有文字那么宽，点菜单空白处会完全没反应。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import ui

from csearch.models.constants import (
    MENU_ITEM_HEIGHT,
    MENU_PANEL_PADDING,
    MENU_WIDTH,
)
from csearch.models.enums import MenuKind
from csearch.view.theme import (
    BORDER,
    FS,
    HINT,
    HOVER,
    RAD,
    SP,
    SURFACE,
    TEXT,
    danger,
    floating_shadow,
    radius_all,
    sym_padding,
)
from csearch.viewmodel.context import AppContext

_ITEM_WIDTH = MENU_WIDTH - MENU_PANEL_PADDING * 2

#: 不带组合符、但确实是「按键」的提示。其余不带 ``+`` 的提示（如"双击路径"）
#: 是操作说明而不是按键，给它们套键帽反而会让人去找那个键，保持普通小字。
_BARE_KEYS = frozenset({"Enter", "Delete", "Esc", "Tab", "F5"})


def _hint(hint: str) -> ui.Control | None:
    """菜单行尾的提示：按键给键帽，说明给一行小字。"""
    if not hint:
        return None
    if "+" in hint or hint in _BARE_KEYS:
        return ui.Kbd(hint)
    return ui.Text(hint, size=FS["caption"], color=HINT, no_wrap=True)


@ui.component
def _MenuItem(
    label: str,
    on_select: Callable[[], None],
    hint: str = "",
    destructive: bool = False,
) -> ui.Control:
    """单条菜单项（hover 高亮 + 点击分发）。

    破坏性操作用 ``danger`` 语义色，而不是加粗或加图标 —— 颜色是最省注意力的
    风险提示，且不会让菜单项的高度/对齐发生变化。
    """
    hover, set_hover = ui.use_state(False)
    trailing = _hint(hint)
    return ui.Container(
        width=_ITEM_WIDTH,
        height=MENU_ITEM_HEIGHT,
        padding=sym_padding(SP["3"], 0),
        border_radius=radius_all(RAD["md"]),
        bgcolor=HOVER if hover else ui.Colors.TRANSPARENT,
        on_click=lambda e: on_select(),
        on_hover=lambda e: set_hover(e.data == "true"),
        content=ui.Row(
            spacing=SP["2"],
            controls=[
                ui.Text(
                    label,
                    size=FS["body"],
                    color=danger() if destructive else TEXT,
                    expand=True,
                    no_wrap=True,
                    overflow=ui.TextOverflow.ELLIPSIS,
                ),
                *([trailing] if trailing else []),
            ],
        ),
    )


def _action(ctx: AppContext, fn: Callable[[], None]) -> Callable[[], None]:
    """包装菜单项动作：先关掉覆盖层，再执行动作。

    必须关，否则是「右键只能用一次」的经典坑：遮罩是全屏且可命中的，菜单一直挂着
    就等于在整张列表上盖了一层透明板，之后所有点击（含下一次右键）都落在遮罩上，
    行手势再也收不到。
    """

    def run() -> None:
        ctx.menu.close()
        fn()

    return run


def _separator() -> ui.Control:
    return ui.Container(
        height=1,
        bgcolor=BORDER,
        margin=ui.Padding(0, SP["1"], 0, SP["1"]),
    )


# --------------------------------------------------------------------- 结果行菜单
def _result_items(ctx: AppContext) -> list[ui.Control]:
    """结果行菜单项：动作在点击瞬间读取 state.menu_row 对应的目标行。"""
    index = ctx.state.menu_row

    return [
        _MenuItem(
            "打开",
            _action(ctx, lambda: asyncio.create_task(ctx.actions.open_selected())),
            "Enter",
        ),
        _MenuItem(
            "打开所在文件夹",
            _action(ctx, lambda: asyncio.create_task(ctx.actions.reveal_selected())),
            "Ctrl+E",
        ),
        _MenuItem(
            "打开文件夹",
            _action(ctx, lambda: asyncio.create_task(ctx.actions.open_folder(index))),
            "双击路径",
        ),
        _separator(),
        _MenuItem(
            "复制完整路径",
            _action(ctx, lambda: asyncio.create_task(ctx.actions.copy_paths())),
            "Ctrl+D",
        ),
        _MenuItem(
            "复制文件名",
            _action(ctx, lambda: asyncio.create_task(ctx.actions.copy_names())),
        ),
        _MenuItem(
            "设置运行次数…",
            _action(ctx, lambda: ctx.actions.request_run_count(index)),
        ),
        _separator(),
        _MenuItem(
            "删除到回收站",
            _action(ctx, lambda: asyncio.create_task(ctx.actions.delete_selected())),
            "Delete",
            destructive=True,
        ),
    ]


# --------------------------------------------------------------------- 书签菜单
def _bookmark_items(ctx: AppContext) -> list[ui.Control]:
    bookmark = next(
        (bm for bm in ctx.state.bookmarks if bm.id == ctx.state.menu_bookmark), None
    )
    if bookmark is None:
        return []
    return [
        _MenuItem(
            "重命名", _action(ctx, lambda: ctx.bookmarks.open_rename_dialog(bookmark))
        ),
        _separator(),
        _MenuItem(
            "删除",
            _action(ctx, lambda: ctx.bookmarks.delete(bookmark)),
            destructive=True,
        ),
    ]


# --------------------------------------------------------------------- 覆盖层
def _panel(ctx: AppContext, items: list[ui.Control]) -> ui.Control:
    """菜单面板：按指针坐标绝对定位，浮在内容之上（阴影 + 描边）。"""
    return ui.Container(
        left=ctx.state.menu_x,
        top=ctx.state.menu_y,
        width=MENU_WIDTH,
        bgcolor=SURFACE,
        border=ui.Border.all(1, BORDER),
        border_radius=radius_all(RAD["lg"]),
        shadow=floating_shadow(2),
        padding=ui.Padding(
            MENU_PANEL_PADDING, MENU_PANEL_PADDING, MENU_PANEL_PADDING, MENU_PANEL_PADDING
        ),
        content=ui.Column(spacing=0, tight=True, controls=items),
    )


def menu_layer(ctx: AppContext) -> list[ui.Control]:
    """右键菜单覆盖层控件列表（未打开时返回空列表，直接展开进根 Stack）。"""
    if ctx.state.menu_kind is None:
        return []
    items = (
        _result_items(ctx)
        if ctx.state.menu_kind is MenuKind.RESULT_ROW
        else _bookmark_items(ctx)
    )
    if not items:
        return []
    return [
        ui.Container(  # 遮罩：点击别处关闭
            left=0,
            top=0,
            right=0,
            bottom=0,
            bgcolor=ui.Colors.TRANSPARENT,
            on_click=lambda e: ctx.menu.close(),
        ),
        _panel(ctx, items),
    ]
