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


def _search_field_key(state: AppState) -> str:
    """搜索框的 diff key：焦点域切换时换 key 重挂载，用 autofocus 抢回焦点。"""
    return (
        f"search-{state.focus_epoch}" if state.focus == Focus.SEARCH else "search"
    )


def _search_field(state: AppState, text: str) -> ft.TextField:
    """构造搜索框控件（只在需要新建时调用）。

    为什么 ``value`` 不给 ``state.query`` 做逐帧绑定（重要，改前先读）：

    搜索框一旦是「受控组件」，flet 的 diff 就会把上一次渲染写入的 ``value``
    与本次渲染的 ``value`` 作比较，不等就下发 replace。而中文输入法组合期间，
    客户端的文本（含 preedit 拼音）**领先于** Python 侧的 ``state.query``：
    事件还在路上、重绘已经执行，于是下发的是「过期文本」，Flutter 侧
    ``TextEditingController.text`` 被重置、composing region 被清空 —— 表现为
    拼音打一半被吃掉、候选框闪烁消失、已上屏的字被覆盖。

    实测（探针记录到的真实中文输入现场）::

        *** PATCH TF.value: 're你v' -> 'rea'
        *** PATCH TF.value: '好好avbvb' -> 'read'

    因此这里改由 ``SearchBar`` 用 use_memo 长期持有同一个控件实例：打字期间
    依赖不变 → 复用实例 → flet 走「原地比较」，``_dirty`` 为空 → 零下发，
    IME 组合完全不受干扰。新建时机仅有：首次挂载、焦点域切换、正则开关切换、
    程序化写入（``state.query_set_seq`` 推进）。
    """
    return ft.TextField(
        value=text,
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
            ft.TextSelection(base_offset=0, extent_offset=len(text))
            if services.select_on_focus and text
            else None
        ),
        key=_search_field_key(state),
        on_change=lambda e: on_query_changed(state, e.control.value),
        on_submit=lambda e: asyncio.create_task(submit(state)),
        on_focus=lambda e: _on_search_focus(state),
    )


def _on_search_focus(state: AppState) -> None:
    """搜索框获得焦点：记录焦点态，并消费「唤回全选」一次性标记。

    标记在非可观测的 services 上，消费它不触发重绘，因此不会打断正在进行的
    输入法组合。
    """
    if state.focus != Focus.SEARCH:
        state.focus = Focus.SEARCH
    services.select_on_focus = False


@ft.component
def SearchBar(state: AppState):
    # 已消费到的程序化写入序号（ref 的读写不触发重绘）
    seen = ft.use_ref(lambda: state.query_set_seq)

    def _field_text() -> str:
        """决定这次新建搜索框时写入的文本。"""
        if state.query_set_seq != seen.current:
            # 程序化写入（Esc 清空 / 应用书签 / 启动回填）：显式下发一次
            seen.current = state.query_set_seq
            return state.query_set
        # 其余重建（焦点域切换 / 正则开关）：沿用当前查询串。此刻用户已停手，
        # state.query 与输入框文本一致，不会吃掉正在输入的字符。
        return state.query

    search_field = ft.use_memo(
        lambda: _search_field(state, _field_text()),
        # 依赖刻意不含 state.query / state.results / state.searching：
        # 打字与结果更新都不应让搜索框控件重建或被下发属性。
        [state.use_regex, state.focus, state.focus_epoch, state.query_set_seq],
    )

    def _build() -> ft.Control:
        return ft.Container(
            padding=sym_padding(12, 8),
            bgcolor=C.SURFACE,
            border=bottom_border(),
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.SEARCH, color=C.TEXT_SUB, size=20),
                    search_field,
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

    # 整树记忆化：搜索栏只由「搜索框实例 + 正则开关 + 三个筛选值」决定外观，
    # 打字、结果更新、选中变化都不该让它重建（flet 的 observable 是对象级通知，
    # 不做这层缓存的话每个 state 字段变化都会把整条工具栏重建一遍）。
    return ft.use_memo(
        _build,
        [
            search_field,
            state.use_regex,
            state.category,
            state.time_range,
            state.size_range,
        ],
    )
