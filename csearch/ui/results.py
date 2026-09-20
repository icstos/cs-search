"""结果列表：表头（可拖拽列宽 / 点击排序）+ 虚拟 ListView + 右键菜单 + 空态。

性能设计（这是本文件最需要维护的部分，改前务必先读）：

flet 的 ``Observable`` 通知是**对象级**的——``state`` 上任何字段变化都会让所有引用
它的组件重排。而 diff（``flet.controls.object_patch``）对列表项**没有同一性短路**：
``_compare_lists`` 会无条件对每一对元素走一遍 ``_compare_dataclasses``。所以「整批行
一起重建」是这里的头号性能陷阱——实测 400 行规模下，点一下选中就要 ~105ms。

两层记忆化把它压下去：

1. **行控件缓存**（``_build_rows``）：行的有效输入只有「行号 / 条目 / 运行次数 /
   是否选中 / 各列宽度」五项，任一不变就复用上一次那个**同一个控件对象**。
   于是点击选中只新建 2 行，而不是 200 行；
2. **整树记忆化**（``Results`` 里的第二个 ``use_memo``）：把返回给上层的整棵树缓存住。
   ``Component.update`` 是以 ``{"_b": <根控件>}`` 形式做 diff 的，这是个**单子字段的
   dataclass 字段**——会命中 diff 里的同一性短路，于是与结果列表无关的状态变化
   （hover 列分隔条、max_ext 之类）几乎是零开销。
"""

from __future__ import annotations

import asyncio

import flet as ft

from csearch.constants import COLUMNS, DEFAULT_COL_WIDTHS, ROW_HEIGHT
from csearch.controller import (
    end_col_drag_gesture,
    launch_everything,
    load_more,
    no_more_to_load,
    on_row_click,
    on_sort,
    open_row_menu,
    start_col_drag,
    start_col_drag_gesture,
    update_col_drag_gesture,
)
from csearch.models import ResultItem
from csearch.state import AppState, services
from csearch.ui.bookmarks import BookmarksPanel
from csearch.ui.icons import icon_for
from csearch.ui.theme import ALIGNMENT, TEXT_ALIGN, C, sym_padding

# 结果 ListView 引用（controller 程序化滚动用），组件注册
services.results_list = ft.Ref[ft.ListView]()


# --------------------------------------------------------------------- 行控件缓存
# 键 = (行号, id(条目), 运行次数, 是否选中, 各列宽度)；值 = (条目, 控件)
# 值里持有条目强引用：既保证 id() 不会被回收后复用，也保证「同一条目」可校验。
_row_cache: dict[tuple, tuple[ResultItem, ft.Control]] = {}


def _widths_key(state: AppState) -> tuple[int, ...]:
    """当前生效的列宽（拖拽期间用低频快照，松手后对齐最终宽度）。"""
    widths = state.row_width_snap or state.col_widths
    return tuple(widths.get(col, DEFAULT_COL_WIDTHS.get(col, 100)) for col, _, _ in COLUMNS)


def _clear_row_cache() -> None:
    """清空行缓存（这些行已不在树上，绝不能在下一次渲染里被复用）。"""
    if _row_cache:
        _row_cache.clear()


def _build_rows(state: AppState, widths: tuple[int, ...]) -> list[ft.Control]:
    """构建/复用结果行：只新建输入真正变化的行，其余复用同一控件对象。

    严格淘汰：本次渲染结束后缓存里只剩下**确实在树上**的条目。这样被移出列表的行
    控件会立刻失去引用，绝不可能被之后某次渲染复用一个已卸载的控件。
    """
    selected = state.selected
    used: dict[tuple, tuple[ResultItem, ft.Control]] = {}
    rows: list[ft.Control] = []

    for index, item in enumerate(state.results):
        key = (index, id(item), item.run_count, index in selected, widths)
        cached = _row_cache.get(key)
        if cached is not None:
            used[key] = cached
            rows.append(cached[1])
            continue
        control = _build_row(state, item, index)
        used[key] = (item, control)
        rows.append(control)

    _row_cache.clear()
    _row_cache.update(used)
    return rows


# --------------------------------------------------------------------- 单行
def _build_row(state: AppState, item: ResultItem, index: int) -> ft.Control:
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
    selected = index in state.selected
    widths = state.row_width_snap or state.col_widths

    def _cell_content(col: str, align: int) -> ft.Control:
        if col == "name":
            icon_name, icon_color = icon_for(item.name, item.is_folder)
            return ft.Row(
                spacing=6,
                controls=[
                    ft.Icon(icon_name, size=16, color=icon_color),
                    ft.Text(
                        item.name,
                        size=13,
                        color=C.ON_PRIMARY if selected else C.TEXT,
                        no_wrap=True,
                        expand=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
            )
        if col == "path":
            return ft.Text(
                item.path,
                size=12,
                color=C.TEXT_SUB,
                no_wrap=True,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        if col == "size":
            return ft.Text(
                item.size_str,
                size=12,
                color=C.TEXT_SUB,
                text_align=TEXT_ALIGN[align],
                no_wrap=True,
            )
        if col == "mtime":
            return ft.Text(
                item.date_str,
                size=12,
                color=C.TEXT_SUB,
                text_align=TEXT_ALIGN[align],
                no_wrap=True,
            )
        return ft.Text(  # run_count
            str(item.run_count) if item.run_count else "",
            size=12,
            color=C.SUCCESS if item.run_count else C.TEXT_FAINT,
            weight=ft.FontWeight.W_600 if item.run_count else ft.FontWeight.W_400,
            text_align=TEXT_ALIGN[align],
            no_wrap=True,
        )

    def _cells() -> list[ft.Control]:
        cells: list[ft.Control] = []
        for col, _title, align in COLUMNS:
            width = widths.get(col, DEFAULT_COL_WIDTHS.get(col, 100))
            # 显式宽度：Column/Row 的松约束下不给宽度会收缩到内容尺寸，可点区域随之缩水
            cells.append(
                ft.GestureDetector(
                    mouse_cursor=ft.MouseCursor.CLICK,
                    on_tap=lambda e, c=col: on_row_click(state, index, c),
                    content=ft.Container(
                        width=width,
                        padding=sym_padding(8, 6),
                        alignment=ALIGNMENT[align],
                        content=_cell_content(col, align),
                    ),
                )
            )
        return cells

    return ft.GestureDetector(
        mouse_cursor=ft.MouseCursor.CLICK,
        on_tap=lambda e: on_row_click(state, index),
        on_secondary_tap_down=lambda e: open_row_menu(state, index, e),
        content=ft.Container(
            height=ROW_HEIGHT,
            bgcolor=C.PRIMARY_CONTAINER
            if selected
            else (C.SURFACE_ALT if index % 2 else C.SURFACE),
            content=ft.Row(spacing=0, controls=_cells()),
        ),
    )


# --------------------------------------------------------------------- 表头
def _header_cell(state: AppState, col: str, title: str, width: int) -> ft.Control:
    active = state.sort_col == col
    arrow = ""
    if active:
        arrow = " ▲" if not state.sort_desc else " ▼"
    return ft.GestureDetector(
        on_tap=lambda e: on_sort(state, col),
        mouse_cursor=ft.MouseCursor.CLICK,
        content=ft.Container(
            width=width,
            padding=sym_padding(8, 6),
            content=ft.Text(
                f"{title}{arrow}",
                size=12,
                weight=ft.FontWeight.W_600,
                color=C.PRIMARY if active else C.TEXT_SUB,
                no_wrap=True,
            ),
        ),
    )


def _separator(state: AppState, col: str) -> ft.Control:
    """列分隔条：外层水平拖拽手势 + 内层按下轮询（双通道兜底）。"""
    active = state.drag_col == col or state.hover_col == col
    bar = ft.Container(
        width=10,
        content=ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=2,
                    expand=True,
                    bgcolor=C.TEXT_HINT if active else C.DIVIDER,
                )
            ],
        ),
    )
    inner = ft.GestureDetector(
        content=bar,
        mouse_cursor=ft.MouseCursor.RESIZE_COLUMN,
        on_tap_down=lambda e: asyncio.create_task(start_col_drag(state, col)),
    )
    return ft.GestureDetector(
        content=inner,
        on_horizontal_drag_start=lambda e: start_col_drag_gesture(state, col, e),
        on_horizontal_drag_update=lambda e: update_col_drag_gesture(state, col, e),
        on_horizontal_drag_end=lambda e: end_col_drag_gesture(state),
        on_hover=lambda e: setattr(
            state, "hover_col", col if e.data == "true" else None
        ),
    )


def _table_header(state: AppState) -> ft.Control:
    cells: list[ft.Control] = []
    for col, title, _align in COLUMNS:
        width = state.col_widths.get(col, DEFAULT_COL_WIDTHS.get(col, 100))
        cells.append(_header_cell(state, col, title, width))
        cells.append(_separator(state, col))
    total = sum(
        state.col_widths.get(c, DEFAULT_COL_WIDTHS.get(c, 100)) for c, _, _ in COLUMNS
    )
    return ft.Container(
        height=32,
        bgcolor=C.HEADER_BG,
        border=ft.Border(
            top=ft.BorderSide(1, C.BORDER), bottom=ft.BorderSide(1, C.BORDER)
        ),
        content=ft.Row(
            spacing=0,
            width=total + 40,
            controls=cells,
        ),
    )


# --------------------------------------------------------------------- 空态
def _engine_down_card(state: AppState) -> ft.Control:
    return ft.Container(
        expand=True,
        alignment=ft.Alignment(0, 0),
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
            controls=[
                ft.Icon(ft.Icons.ERROR_OUTLINE, size=48, color=C.DANGER),
                ft.Text("Everything 服务未运行", size=16, weight=ft.FontWeight.W_600),
                ft.Text(
                    state.engine_msg or "请启动 Everything 后使用",
                    size=13,
                    color=C.TEXT_SUB,
                ),
                ft.FilledButton(
                    "一键启动 Everything",
                    icon=ft.Icons.PLAY_ARROW,
                    on_click=lambda e: launch_everything(),
                ),
            ],
        ),
    )


def _empty_hint() -> ft.Control:
    return ft.Container(
        expand=True,
        alignment=ft.Alignment(0, 0),
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
            controls=[
                ft.Icon(ft.Icons.SEARCH_OFF, size=48, color=C.TEXT_HINT),
                ft.Text("无匹配结果", size=14, color=C.TEXT_HINT),
            ],
        ),
    )


# --------------------------------------------------------------------- 列表
@ft.component
def Results(state: AppState):
    widths_key = _widths_key(state)

    # 关键：行控件在「任何早返回之前」无条件用 use_memo 声明依赖。这样组件在空查询
    # （返回书签面板）的首次挂载阶段就已订阅结果集，之后结果分片落地、选中变化都会
    # 触发重渲染；否则首次挂载走早返回分支、从未读取 results，切到列表分支后将收不到
    # 后续更新（列表冻结）。
    rows = ft.use_memo(
        lambda: _build_rows(state, widths_key),
        [
            state.results,
            state.selected,
            # 刻意只依赖「生效列宽」这一派生值，而不是 state.col_widths：
            # 拖拽期间 col_widths 每帧都在变，若直接依赖它就会每帧整批重建所有行。
            # 生效列宽在拖拽时取低频快照（row_width_snap），松手才对齐最终值。
            widths_key,
        ],
    )

    def _on_scroll_event(e) -> None:
        pixels = float(e.pixels or 0)
        max_ext = float(e.max_scroll_extent or 0)
        # 持续同步真实滚动位置，滚轮桥据此做绝对偏移
        services.wheel_acc = pixels
        state.max_ext = max_ext
        viewport = float(e.viewport_dimension or 0)
        # 接近底部自动加载下一页（硬边界处不再触发，避免越界弹动）
        if (
            max_ext > 0
            and not no_more_to_load(state)
            and pixels + viewport >= max_ext - 120
        ):
            asyncio.create_task(load_more(state))

    empty_query = not state.query.strip()

    def _build() -> ft.Control:
        if not state.engine_ok:
            _clear_row_cache()
            return _engine_down_card(state)

        # 搜索框为空：展示书签面板（行 memo 已在上方无条件求值，订阅不丢）
        if empty_query:
            _clear_row_cache()
            return BookmarksPanel(state)

        # 注意：ft.Scrollbar 是滚动条「配置对象」而非容器控件，必须通过 ListView 的
        # scroll= 属性传入；把它当控件包裹 content 会在挂载该分支时使组件 fiber 失效
        # （表现为结果列表首次渲染后永久冻结、不再随输入更新）。
        list_view = ft.ListView(
            ref=services.results_list,
            controls=rows,
            expand=True,
            spacing=0,
            padding=ft.Padding(0, 4, 0, 4),
            item_extent=ROW_HEIGHT,  # 固定行高：懒加载精确估算滚动范围
            build_controls_on_demand=True,  # 虚拟构建，仅渲染可视行，长列表高性能
            scroll=ft.Scrollbar(
                thumb_visibility=True, track_visibility=True, thickness=10
            ),
            on_scroll=_on_scroll_event,
        )

        # 注意：Stack 的子控件只放「此刻真的需要显示的」。
        # 绝不要写成 `... else ft.Container()` 这种空容器占位 —— 空 Container 在 Stack
        # 的松约束下会被撑成整个 Stack 大小，而且**是可命中的**（实测由最小复现确认），
        # 于是它成了盖在结果列表上的一层全尺寸透明遮罩，把行的单击/双击/右键全部吞掉。
        # 症状极具迷惑性：表头在 Stack 外面，点击排序一切正常，只有结果行毫无反应。
        overlay: list[ft.Control] = []
        if state.searching:
            overlay.append(
                ft.ProgressRing(width=20, height=20, stroke_width=2, left=12, top=8)
            )
        if not state.searching and not rows:
            overlay.append(_empty_hint())

        return ft.Column(
            expand=True,
            spacing=0,
            controls=[
                _table_header(state),
                ft.Container(
                    expand=True,
                    bgcolor=C.SURFACE,
                    content=ft.Stack(expand=True, controls=[list_view, *overlay]),
                ),
            ],
        )

    # 整树记忆化：返回同一个根控件对象时，flet 对 {"_b": 根控件} 的 diff 会走
    # dataclass 同一性短路，整棵子树零遍历。依赖必须覆盖「影响外观」的全部输入。
    return ft.use_memo(
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
        ],
    )
