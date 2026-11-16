"""结果列表：表头（可拖拽列宽 / 点击排序）+ 虚拟 ListView + 右键菜单 + 空态。

本层零业务逻辑：行组件由 ``ctx.state`` 派生，交互转发给 ViewModel。

视觉基线（cs-ui / M3）：列表是一块平整的内容面 —— 没有斑马纹，靠「选中态」
承担位置反馈（与资源管理器、Everything 的桌面直觉一致）；表头用一层稍高的
容器色与列表区分，列宽分隔条只在悬停/拖拽时浮现。

性能设计（这是本文件最需要维护的部分，改前务必先读）：

flet 的 ``Observable`` 通知是**对象级**的——``state`` 上任何字段变化都会让所有引用
它的组件重排。而 diff（``flet.controls.object_patch``）对列表项**没有同一性短路**：
``_compare_lists`` 会无条件对每一对元素走一遍 ``_compare_dataclasses``。所以「整批行
一起重建」是这里的头号性能陷阱——实测 400 行规模下，点一下选中就要 ~105ms。

两层记忆化把它压下去：

1. **行控件缓存**（``_build_rows``）：行的有效输入只有「行号 / 条目 / 运行次数 /
   是否选中 / 各列宽度 / 主题模式」六项，任一不变就复用上一次那个**同一个控件对象**。
   于是点击选中只新建 2 行，而不是 200 行；
2. **整树记忆化**（``Results`` 里的第二个 ``use_memo``）：把返回给上层的整棵树缓存住。
   ``Component.update`` 是以 ``{"_b": <根控件>}`` 形式做 diff 的，这是个**单子字段的
   dataclass 字段**——会命中 diff 里的同一性短路，于是与结果列表无关的状态变化
   （hover 列分隔条、max_ext 之类）几乎是零开销。
"""

from __future__ import annotations

import asyncio

import ui

from csearch.models.constants import (
    COLUMNS,
    DEFAULT_COL_WIDTHS,
    HEADER_HEIGHT,
    ROW_HEIGHT,
)
from csearch.models.entities import ResultItem
from csearch.view.bookmarks import BookmarksPanel
from csearch.view.events import hover_entered, pointer_dx, pointer_position
from csearch.view.icons import icon_for
from csearch.view.scroller import results_list_ref
from csearch.view.theme import (
    ACCENT,
    ALIGNMENT,
    BORDER,
    FAINT,
    FS,
    FW,
    HEADER,
    ICON,
    ON_SELECTED,
    SELECTED_BG,
    SP,
    SUB_ON_SELECTED,
    SURFACE,
    TEXT,
    TEXT_ALIGN,
    TEXT_SUB,
    TRACK,
    danger,
    radius_all,
    success,
    sym_padding,
)
from csearch.viewmodel.context import AppContext
from csearch.viewmodel.state import AppState

# --------------------------------------------------------------------- 行控件缓存
# 键 = (行号, id(条目), 运行次数, 是否选中, 各列宽度, 主题模式)；值 = (条目, 控件)
# 值里持有条目强引用：既保证 id() 不会被回收后复用，也保证「同一条目」可校验。
_row_cache: dict[tuple, tuple[ResultItem, ui.Control]] = {}


def _widths_key(state: AppState) -> tuple[int, ...]:
    """当前生效的列宽（拖拽期间用低频快照，松手后对齐最终宽度）。"""
    widths = state.row_width_snap or state.col_widths
    return tuple(
        widths.get(col, DEFAULT_COL_WIDTHS.get(col, 100)) for col, _, _ in COLUMNS
    )


def _mode_key() -> str:
    """当前实际生效的明暗模式。

    必须进缓存键：个别颜色（运行次数用 ``success`` 语义色）是按模式取值的
    ``#RRGGBB``，不会随 Flutter 的 ColorScheme 自动重解析。少了这一项，
    切主题后已有的行会停在旧模式的绿色上。
    """
    return ui.core.theme.current_mode()


def _clear_row_cache() -> None:
    """清空行缓存（这些行已不在树上，绝不能在下一次渲染里被复用）。"""
    if _row_cache:
        _row_cache.clear()


def _build_rows(ctx: AppContext, widths: tuple[int, ...]) -> list[ui.Control]:
    """构建/复用结果行：只新建输入真正变化的行，其余复用同一控件对象。

    严格淘汰：本次渲染结束后缓存里只剩下**确实在树上**的条目。这样被移出列表的行
    控件会立刻失去引用，绝不可能被之后某次渲染复用一个已卸载的控件。
    """
    state = ctx.state
    selected = state.selected
    mode = _mode_key()
    used: dict[tuple, tuple[ResultItem, ui.Control]] = {}
    rows: list[ui.Control] = []

    for index, item in enumerate(state.results):
        key = (index, id(item), item.run_count, index in selected, widths, mode)
        cached = _row_cache.get(key)
        if cached is not None:
            used[key] = cached
            rows.append(cached[1])
            continue
        control = _build_row(ctx, item, index)
        used[key] = (item, control)
        rows.append(control)

    _row_cache.clear()
    _row_cache.update(used)
    return rows


# --------------------------------------------------------------------- 单行
def _build_row(ctx: AppContext, item: ResultItem, index: int) -> ui.Control:
    """构建单行控件（普通函数，由 _build_rows 按需调用）。

    选中态 / 列宽的变化通过 _build_rows 的缓存键驱动单行重建，不再整批重建，
    因此这里可以放心地按「当前状态」直接构建。

    手势分层（实测结论，改动前请先读）：
    - 每个单元格各挂一个 GestureDetector —— 内层声明的手势由内层处理，
      因此单击/双击能拿到「点在哪个列」，路径列才能单独走「打开所在文件夹」；
    - 外层 GestureDetector 只声明 ``on_secondary_tap_down``（内层未声明，仍会被
      外层接住）与兜底的 ``on_tap``（行右侧空白区），负责右键菜单与空白区选中；
    - 同一控件上 ``on_tap`` + ``on_double_tap`` 互斥会拖慢单击响应，故双击在
      ``on_row_click`` 里用手动时间窗判定。
    """
    state = ctx.state
    selected = index in state.selected
    widths = state.row_width_snap or state.col_widths
    primary = ON_SELECTED if selected else TEXT
    secondary = SUB_ON_SELECTED if selected else TEXT_SUB

    def _cell_content(col: str, align: int) -> ui.Control:
        if col == "name":
            icon_name, icon_color = icon_for(item.name, item.is_folder)
            return ui.Row(
                spacing=SP["2"],
                controls=[
                    ui.Icon(icon_name, size=ICON["md"], color=icon_color),
                    ui.Text(
                        item.name,
                        size=FS["body"],
                        color=primary,
                        no_wrap=True,
                        expand=True,
                        overflow=ui.TextOverflow.ELLIPSIS,
                    ),
                ],
            )
        if col == "path":
            return ui.Text(
                item.path,
                size=FS["small"],
                color=secondary,
                no_wrap=True,
                overflow=ui.TextOverflow.ELLIPSIS,
            )
        if col == "size":
            return ui.Text(
                item.size_str,
                size=FS["small"],
                color=secondary,
                text_align=TEXT_ALIGN[align],
                no_wrap=True,
            )
        if col == "mtime":
            return ui.Text(
                item.date_str,
                size=FS["small"],
                color=secondary,
                text_align=TEXT_ALIGN[align],
                no_wrap=True,
            )
        return ui.Text(  # run_count
            str(item.run_count) if item.run_count else "",
            size=FS["small"],
            color=success() if item.run_count else FAINT,
            weight=FW["semibold"] if item.run_count else FW["regular"],
            text_align=TEXT_ALIGN[align],
            no_wrap=True,
        )

    def _cells() -> list[ui.Control]:
        cells: list[ui.Control] = []
        for col, _title, align in COLUMNS:
            width = widths.get(col, DEFAULT_COL_WIDTHS.get(col, 100))
            # 显式宽度：Column/Row 的松约束下不给宽度会收缩到内容尺寸，可点区域随之缩水
            cells.append(
                ui.GestureDetector(
                    mouse_cursor=ui.MouseCursor.CLICK,
                    on_tap=lambda e, c=col: ctx.selection.on_row_click(index, c),
                    content=ui.Container(
                        width=width,
                        padding=sym_padding(SP["2"], SP["1"]),
                        alignment=ALIGNMENT[align],
                        content=_cell_content(col, align),
                    ),
                )
            )
        return cells

    return ui.GestureDetector(
        mouse_cursor=ui.MouseCursor.CLICK,
        on_tap=lambda e: ctx.selection.on_row_click(index),
        on_secondary_tap_down=lambda e: ctx.menu.open_row(index, *pointer_position(e)),
        content=ui.Container(
            height=ROW_HEIGHT,
            bgcolor=SELECTED_BG if selected else ui.Colors.TRANSPARENT,
            content=ui.Row(spacing=0, controls=_cells()),
        ),
    )


# --------------------------------------------------------------------- 表头
def _header_cell(ctx: AppContext, col: str, title: str, width: int) -> ui.Control:
    state = ctx.state
    active = state.sort_col == col
    arrow = ""
    if active:
        arrow = " ▲" if not state.sort_desc else " ▼"
    return ui.GestureDetector(
        on_tap=lambda e: ctx.search.on_sort(col),
        mouse_cursor=ui.MouseCursor.CLICK,
        content=ui.Container(
            width=width,
            padding=sym_padding(SP["2"], SP["1"]),
            content=ui.Text(
                f"{title}{arrow}",
                size=FS["small"],
                weight=FW["semibold"],
                color=ACCENT if active else TEXT_SUB,
                no_wrap=True,
            ),
        ),
    )


def _separator(ctx: AppContext, col: str) -> ui.Control:
    """列分隔条：外层水平拖拽手势 + 内层按下轮询（双通道兜底）。"""
    state = ctx.state
    active = state.drag_col == col or state.hover_col == col
    bar = ui.Container(
        width=10,
        content=ui.Row(
            alignment=ui.MainAxisAlignment.CENTER,
            controls=[
                ui.Container(
                    width=2,
                    expand=True,
                    bgcolor=TRACK if active else ui.Colors.TRANSPARENT,
                    border_radius=radius_all(1),
                )
            ],
        ),
    )
    inner = ui.GestureDetector(
        content=bar,
        mouse_cursor=ui.MouseCursor.RESIZE_COLUMN,
        on_tap_down=lambda e: asyncio.create_task(ctx.columns.start_drag(col)),
    )
    return ui.GestureDetector(
        content=inner,
        on_horizontal_drag_start=lambda e: ctx.columns.start_drag_gesture(
            col, pointer_dx(e)
        ),
        on_horizontal_drag_update=lambda e: ctx.columns.update_drag_gesture(
            col, pointer_dx(e)
        ),
        on_horizontal_drag_end=lambda e: ctx.columns.end_drag_gesture(),
        on_hover=lambda e: ctx.columns.set_hover(col if hover_entered(e) else None),
    )


def _table_header(ctx: AppContext) -> ui.Control:
    state = ctx.state
    cells: list[ui.Control] = []
    for col, title, _align in COLUMNS:
        width = state.col_widths.get(col, DEFAULT_COL_WIDTHS.get(col, 100))
        cells.append(_header_cell(ctx, col, title, width))
        cells.append(_separator(ctx, col))
    total = sum(
        state.col_widths.get(c, DEFAULT_COL_WIDTHS.get(c, 100)) for c, _, _ in COLUMNS
    )
    return ui.Container(
        height=HEADER_HEIGHT,
        bgcolor=HEADER,
        border=ui.Border(bottom=ui.BorderSide(1, BORDER)),
        content=ui.Row(spacing=0, width=total + 40, controls=cells),
    )


# --------------------------------------------------------------------- 空态
def _engine_down_card(ctx: AppContext) -> ui.Control:
    """引擎故障页：图标 + 说明 + 一键启动，整块居中。

    这一块没有走 ``empty_block``：它需要一个**主操作按钮**，而且图标要带危险色
    （故障不是"这里暂时空着"，是"坏了一件事"）。其余留白与空态保持同一套间距。
    """
    return ui.Container(
        expand=True,
        bgcolor=SURFACE,
        alignment=ui.Alignment(0, 0),
        content=ui.Column(
            alignment=ui.MainAxisAlignment.CENTER,
            horizontal_alignment=ui.CrossAxisAlignment.CENTER,
            spacing=SP["3"],
            controls=[
                ui.Icon(
                    ui.Icons.DESKTOP_ACCESS_DISABLED_OUTLINED,
                    size=ICON["3xl"],
                    color=danger(),
                ),
                ui.Text(
                    "Everything 服务未运行",
                    size=FS["title"],
                    weight=FW["semibold"],
                    color=TEXT,
                ),
                ui.Text(
                    ctx.state.engine_msg or "启动 Everything 后即可开始搜索",
                    size=FS["body"],
                    color=TEXT_SUB,
                ),
                ui.FilledButton(
                    "一键启动 Everything",
                    icon=ui.Icons.PLAY_ARROW,
                    on_click=lambda e: ctx.actions.launch_everything(),
                ),
            ],
        ),
    )


def _empty_hint() -> ui.Control:
    """搜到 0 条：走 cs-ui 的整块空态，图标底座 + 主文 + 下一步提示。"""
    return ui.empty_block(
        "没有匹配的文件",
        hint="换个更短的关键词，或放宽筛选条件",
        icon=ui.Icons.SEARCH_OFF,
        height=None,  # 由 Stack 撑开，居中
    )


# --------------------------------------------------------------------- 列表
@ui.component
def Results(ctx: AppContext):
    state = ctx.state
    widths_key = _widths_key(state)

    # 关键：行控件在「任何早返回之前」无条件用 use_memo 声明依赖。这样组件在空查询
    # （返回书签面板）的首次挂载阶段就已订阅结果集，之后结果分片落地、选中变化都会
    # 触发重渲染；否则首次挂载走早返回分支、从未读取 results，切到列表分支后将收不到
    # 后续更新（列表冻结）。
    rows = ui.use_memo(
        lambda: _build_rows(ctx, widths_key),
        [
            state.results,
            state.selected,
            # 刻意只依赖「生效列宽」这一派生值，而不是 state.col_widths：
            # 拖拽期间 col_widths 每帧都在变，若直接依赖它就会每帧整批重建所有行。
            # 生效列宽在拖拽时取低频快照（row_width_snap），松手才对齐最终值。
            widths_key,
            # 明暗切换要重算行的语义色（见 _mode_key）
            state.theme_mode,
        ],
    )

    def _on_scroll_event(e) -> None:
        ctx.search.on_scroll(
            pixels=float(e.pixels or 0),
            max_extent=float(e.max_scroll_extent or 0),
            viewport=float(e.viewport_dimension or 0),
        )

    empty_query = not state.query.strip()

    def _build() -> ui.Control:
        if not state.engine_ok:
            _clear_row_cache()
            return _engine_down_card(ctx)

        # 搜索框为空：展示书签面板（行 memo 已在上方无条件求值，订阅不丢）
        if empty_query:
            _clear_row_cache()
            return BookmarksPanel(ctx)

        # 注意：ui.Scrollbar 是滚动条「配置对象」而非容器控件，必须通过 ListView 的
        # scroll= 属性传入；把它当控件包裹 content 会在挂载该分支时使组件 fiber 失效
        # （表现为结果列表首次渲染后永久冻结、不再随输入更新）。
        list_view = ui.ListView(
            ref=results_list_ref,
            controls=rows,
            expand=True,
            spacing=0,
            padding=ui.Padding(0, SP["1"], 0, SP["1"]),
            item_extent=ROW_HEIGHT,  # 固定行高：懒加载精确估算滚动范围
            build_controls_on_demand=True,  # 虚拟构建，仅渲染可视行，长列表高性能
            scroll=ui.Scrollbar(
                thumb_visibility=True, track_visibility=True, thickness=10
            ),
            on_scroll=_on_scroll_event,
        )

        # 注意：Stack 的子控件只放「此刻真的需要显示的」。
        # 绝不要写成 `... else ui.Container()` 这种空容器占位 —— 空 Container 在 Stack
        # 的松约束下会被撑成整个 Stack 大小，而且**是可命中的**（实测由最小复现确认），
        # 于是它成了盖在结果列表上的一层全尺寸透明遮罩，把行的单击/双击/右键全部吞掉。
        # 症状极具迷惑性：表头在 Stack 外面，点击排序一切正常，只有结果行毫无反应。
        overlay: list[ui.Control] = []
        if state.searching:
            # 2px 顶部进度条：不遮内容、不改变布局高度（比转圈更贴合列表语义）
            overlay.append(
                ui.ProgressBar(
                    left=0, top=0, right=0, height=2, color=ACCENT, bar_height=2
                )
            )
        if not state.searching and not rows:
            overlay.append(_empty_hint())

        return ui.Column(
            expand=True,
            spacing=0,
            controls=[
                _table_header(ctx),
                ui.Container(
                    expand=True,
                    bgcolor=SURFACE,
                    content=ui.Stack(expand=True, controls=[list_view, *overlay]),
                ),
            ],
        )

    # 整树记忆化：返回同一个根控件对象时，flet 对 {"_b": 根控件} 的 diff 会走
    # dataclass 同一性短路，整棵子树零遍历。依赖必须覆盖「影响外观」的全部输入。
    return ui.use_memo(
        _build,
        [
            rows,
            empty_query,
            state.engine_ok,
            state.engine_msg,
            state.searching,
            state.col_widths,
            state.drag_col,
            state.hover_col,
            state.sort_col,
            state.sort_desc,
            state.bookmarks,
            state.theme_mode,
        ],
    )
