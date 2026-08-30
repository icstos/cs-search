"""结果列表：可排序表头（列宽可拖拽）+ 交替行背景 + 类型图标 + 右键菜单 + 懒加载 + 键盘导航。

列宽对齐：表头与行统一从 state.col_widths 读取像素宽度，均从 x=0 起无内边距；
对齐规则：名称/路径左对齐，大小右对齐，修改时间居中。
"""

from __future__ import annotations

import asyncio

import flet as ft

from csearch import logic
from csearch.state import AppState, services
from csearch.types import ResultItem
from csearch.ui.bookmarks import BookmarksPanel
from csearch.ui.icons import icon_for

_BORDER, _HEADER_BG, _ROW_H = "#E4E7ED", "#F1F3F4", 30
# (列名, 标题, 对齐: -1 左 / 0 中 / 1 右)
# (列名, 标题, 对齐: -1 左 / 0 中 / 1 右)
# (列名, 标题, 对齐: -1 左 / 0 中 / 1 右)
_COLUMNS = [("name", "名称", -1), ("path", "路径", -1), ("size", "大小", 1),
           ("mtime", "修改时间", 0), ("run_count", "次数", 1)]
_ALIGNMENT = {-1: ft.Alignment(-1, 0), 0: ft.Alignment(0, 0), 1: ft.Alignment(1, 0)}
_TEXT_ALIGN = {-1: ft.TextAlign.LEFT, 0: ft.TextAlign.CENTER, 1: ft.TextAlign.RIGHT}


@ft.component
def Results(state: AppState):
    lv_ref = ft.use_ref(ft.ListView)
    menu_ref = ft.use_ref(None)  # 共享右键菜单 Ref（挂载后由框架赋值）
    # 滚轮桥/键盘翻页需要程序化滚动：把列表 Ref 注册到 services 供 logic 使用
    services.results_list_ref = lv_ref

    # 共享右键菜单：所有行共用一个 ContextMenu（右键时记录目标行再打开），
    # 避免每行内联 8 个菜单项（200 行 → 1600+ 控件）拖慢结果渲染
    def _act(fn):
        def _h(e):
            idx = services.menu_row
            if idx >= 0:
                logic.ensure_selected(state, idx)
            result = fn(state)  # fn 可能是同步或异步（打开/复制/删除等）
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)

        return _h

    def _run_count(e):
        idx = services.menu_row
        if idx >= 0:
            logic.ensure_selected(state, idx)
            logic.request_run_count(state, idx)

    menu = [
        ft.PopupMenuItem(content="打开", icon=ft.Icons.OPEN_IN_NEW, on_click=_act(logic.open_selected)),
        ft.PopupMenuItem(content="打开文件所在位置", icon=ft.Icons.FOLDER_OPEN, on_click=_act(logic.reveal_selected)),
        ft.PopupMenuItem(content="复制完整路径", icon=ft.Icons.CONTENT_COPY, on_click=_act(logic.copy_paths)),
        ft.PopupMenuItem(content="复制文件名", icon=ft.Icons.CONTENT_PASTE, on_click=_act(logic.copy_names)),
        ft.PopupMenuItem(content="设置运行次数", icon=ft.Icons.TIMER, on_click=_run_count),
        ft.PopupMenuItem(),
        ft.PopupMenuItem(content="删除到回收站", icon=ft.Icons.DELETE_OUTLINE, on_click=_act(logic.delete_selected)),
    ]

    def _on_row_secondary(index: int, e) -> None:
        # 右键行（按下即触发，事件携带光标位置）：记录目标行并在光标处打开共享菜单；
        # 菜单项点击时按目标行执行（菜单项与行解耦，渲染开销极低）
        services.menu_row = index
        pos = getattr(e, "global_position", None)
        asyncio.create_task(_open_menu(pos))

    async def _open_menu(pos) -> None:
        m = menu_ref.current
        if m is None:
            return
        try:
            if pos is not None and getattr(pos, "x", None) is not None:
                await m.open(global_position=ft.Offset(pos.x, pos.y))
            else:
                await m.open()
        except Exception:  # noqa: BLE001
            pass

    # 行控件缓存：结果集/选中集/行宽快照变化时重建（拖拽中表头每帧跟手，行按快照节流重排）
    rows = ft.use_memo(
        lambda: [_row(state, i, item, _on_row_secondary) for i, item in enumerate(state.results)],
        [state.results, state.selected, state.row_width_snap],
    )

    def _on_scroll(e) -> None:
        # 触底增量加载：滚轮桥 scroll_to 是跳转，scroll_delta 恒为 0，必须按
        # 像素位置判断（距底部 <150px 时触发）；load_more 内部有并发/上限
        # 防护，重复触发安全。
        pixels = float(getattr(e, "pixels", 0) or 0)
        max_ext = float(getattr(e, "max_scroll_extent", 0) or 0)
        viewport = float(getattr(e, "viewport_dimension", 0) or 0)
        # 同步真实滚动位置：滚轮/键盘/拖拽/增量加载后，累计值跟随实际位置，
        # 保证下一次滚轮从正确位置继续；max_ext 用于滚轮目标夹紧
        services.wheel_acc = pixels
        state.max_ext = max_ext
        if max_ext > 0 and pixels + viewport >= max_ext - 150:
            asyncio.create_task(logic.load_more(state))

    def _on_list_key(e) -> None:
        # 已废弃：列表按键统一由页面级 on_keyboard 处理（KeyboardListener 包裹
        # 会导致 ListView 程序化滚动回弹，见上方注释）
        pass

    if not state.query.strip():
        # 搜索框无内容：连表头一并隐藏，仅展示书签面板
        return BookmarksPanel(state)
    if not state.results and not state.searching:
        body = ft.Container(
            expand=True,
            alignment=ft.Alignment(0, 0),
            content=ft.Text(
                state.engine_msg if not state.engine_ok else "没有匹配的结果",
                size=13,
                color="#9AA0A6",
            ),
        )
    else:
        # 注意：不能用 KeyboardListener 包裹 ListView —— flet 0.86 客户端中该包裹
        # 会使 ListView 的程序化滚动（scroll_to）立即回弹到顶部，滚轮/键盘滚动全部失效。
        # 列表按键统一走页面级 page.on_keyboard_event（见 logic.on_keyboard）。
        # 共享右键菜单包裹（secondary_trigger=None 纯监听，不参与输入/焦点）；
        # ContextMenu 不传递 expand，外层套 Container(expand=True) 保证列表撑满
        body = ft.Container(
            expand=True,
            content=ft.ContextMenu(
                ref=menu_ref,
                items=menu,
                secondary_trigger=None,
                content=ft.ListView(
                    ref=lv_ref,
                    controls=rows,
                    expand=True,
                    spacing=0,
                    padding=ft.Padding(0, 4, 0, 4),
                    build_controls_on_demand=True,
                    item_extent=_ROW_H,  # 行高固定：懒加载精确估算滚动范围
                    scroll=ft.Scrollbar(thumb_visibility=True, track_visibility=True, thickness=10),
                    on_scroll=_on_scroll,
                ),
            ),
        )

    return ft.Column(
        expand=True,
        spacing=0,
        controls=[_header(state), body],
    )


def _header(state: AppState) -> ft.Control:
    cells: list[ft.Control] = []
    for i, (key, label, align) in enumerate(_COLUMNS):
        active = state.sort_col == key
        arrow = ft.Icon(
            ft.Icons.ARROW_DOWNWARD if state.sort_desc else ft.Icons.ARROW_UPWARD,
            size=13, color="#1A73E8",
        ) if active else ft.Container(width=0, height=0)
        cells.append(ft.Container(
            width=state.col_widths.get(key, 90),
            alignment=_ALIGNMENT[align],
            on_click=lambda e, k=key: logic.on_sort(state, k),
            content=ft.Row(
                spacing=2,
                controls=[
                    ft.Text(label, size=12, weight=ft.FontWeight.W_600,
                            color="#1A73E8" if active else "#5F6368"),
                    arrow,
                ],
            ),
        ))
        if i < len(_COLUMNS) - 1:
            cells.append(_separator(state, key))

    return ft.Container(
        bgcolor=_HEADER_BG,
        padding=ft.Padding(8, 6, 8, 6),
        border=ft.Border(bottom=ft.BorderSide(1, _BORDER)),
        content=ft.Row(spacing=0, controls=cells),
    )


def _separator(state: AppState, col: str) -> ft.Control:
    """列宽拖拽分隔条：GestureDetector 水平拖拽事件驱动。"""
    active = state.drag_col == col or state.hover_col == col
    # 双通道：GestureDetector 原生拖拽事件（global_position 计算）+ 内层 Container
    # on_tap_down 启动 ctypes 轮询兜底（flet 拖拽事件数据不可靠时的保险）
    return ft.GestureDetector(
        width=16,
        height=30,
        mouse_cursor=ft.MouseCursor.RESIZE_COLUMN,
        on_horizontal_drag_start=lambda e: logic.start_col_drag_gesture(state, col, e),
        on_horizontal_drag_update=lambda e: logic.update_col_drag_gesture(state, col, e),
        on_horizontal_drag_end=lambda e: logic.end_col_drag_gesture(state),
        on_horizontal_drag_cancel=lambda e: logic.end_col_drag_gesture(state),
        tooltip="拖拽调整列宽",
        content=ft.Container(
            width=16,
            height=30,
            alignment=ft.Alignment(0, 0),
            on_tap_down=lambda e: asyncio.create_task(logic.start_col_drag(state, col)),
            on_hover=lambda e: _hover_col(state, col, e),
            content=ft.Container(
                width=3,
                height=18,
                border_radius=ft.BorderRadius(2, 2, 2, 2),
                bgcolor="#9AA0A6" if active else "#DDE1E6",
            ),
        ),
    )


def _hover_col(state: AppState, col: str, e) -> None:
    state.hover_col = col if getattr(e, "data", "") == "true" else None


def _row(state: AppState, index: int, item: ResultItem,
          on_secondary) -> ft.Control:
    selected = index in state.selected
    bg = "#E8F0FE" if selected else ("#FFFFFF" if index % 2 == 0 else "#F6F8FA")
    icon, color = icon_for(item.name, item.is_folder)
    widths = state.col_widths

    return ft.GestureDetector(
        on_secondary_tap_down=lambda e, i=index: on_secondary(i, e),
        content=ft.Container(
            height=_ROW_H,
            bgcolor=bg,
            on_click=lambda e, i=index: logic.on_row_click(state, i),
            content=ft.Row(
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(icon, size=15, color=color),
                    ft.Text(item.name, size=13,
                            weight=ft.FontWeight.W_500 if selected else None,
                            color="#202124" if not selected else "#174EA6",
                            width=widths.get("name", 260) - 21,  # 预留图标位
                            overflow=ft.TextOverflow.ELLIPSIS, max_lines=1),
                    ft.GestureDetector(
                        width=widths.get("path", 420),
                        on_tap=lambda e, i=index: logic.on_row_click(state, i),
                        on_double_tap=lambda e, i=index: asyncio.create_task(logic.open_folder(state, i)),
                        content=ft.Text(item.path, size=12, color="#5F6368",
                                        width=widths.get("path", 420),
                                        text_align=_TEXT_ALIGN[-1],
                                        overflow=ft.TextOverflow.ELLIPSIS, max_lines=1),
                    ),
                    ft.Text(item.size_str, size=12, color="#5F6368",
                            width=widths.get("size", 90),
                            text_align=_TEXT_ALIGN[1]),
                    ft.Text(item.date_str, size=12, color="#5F6368",
                            width=widths.get("mtime", 140),
                            text_align=_TEXT_ALIGN[0]),
                    ft.Text(str(item.run_count) if item.run_count else "", size=12,
                            color="#188038" if item.run_count else "#BDC1C6",
                            width=widths.get("run_count", 70),
                            text_align=_TEXT_ALIGN[1]),
                ],
            ),
        ),
    )