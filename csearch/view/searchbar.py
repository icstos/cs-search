"""顶部搜索行：搜索框 + 分类/时间/大小筛选 + 正则开关 + 书签/刷新/设置。

本层零业务逻辑：渲染由 ``ctx.state`` 派生，交互一律转发给 ViewModel。

视觉基线：搜索框是唯一的「主输入」，用 M3 描边式 + 主色聚焦环把它顶出来；
筛选器退成无边框的文字按钮（带类型图标），动作按钮保持图标，整条工具栏只有
一个视觉重心。间距与字号全部取自 ``theme`` 的令牌，不写裸数字。
"""

from __future__ import annotations

import asyncio

import ui

from csearch.models.constants import CATEGORIES, SIZE_RANGES, TIME_RANGES
from csearch.models.enums import Focus
from csearch.view.theme import (
    ACCENT,
    ACCENT_BG,
    BORDER,
    FS,
    FW,
    PANEL,
    RAD,
    SP,
    SURFACE,
    TEXT,
    TEXT_SUB,
    TRACK,
    bottom_border,
    field_border,
    radius_all,
    sym_padding,
)
from csearch.viewmodel.context import AppContext
from csearch.viewmodel.state import AppState

_TOOLTIPS = {"category": "文件分类", "time": "修改时间", "size": "文件大小"}


def _regex_toggle(ctx: AppContext) -> ui.Control:
    """正则开关：开启时用主色容器填充，关闭时是安静的描边胶囊。"""
    on = ctx.state.use_regex
    return ui.TextButton(
        content="正则",
        tooltip=(
            "正则搜索：已开启，点击关闭（按正则匹配文件名）"
            if on
            else r"正则搜索：点击开启（参考 Everything，如 ^report.*\.xlsx$）"
        ),
        style=ui.ButtonStyle(
            color=ACCENT if on else TEXT_SUB,
            bgcolor=ACCENT_BG if on else ui.Colors.TRANSPARENT,
            padding=sym_padding(SP["2"], SP["1"]),
            shape=ui.StadiumBorder(),
            side=ui.BorderSide(1, ACCENT if on else BORDER),
            text_style=ui.TextStyle(
                size=FS["small"],
                weight=FW["semibold"] if on else FW["medium"],
            ),
        ),
        on_click=lambda e: ctx.search.toggle_regex(),
    )


def _divider() -> ui.Control:
    """工具栏内的分组竖线（比整条 VerticalDivider 轻，不参与布局分配）。"""
    return ui.Container(width=1, height=18, bgcolor=TRACK, margin=sym_padding(2, 0))


def _dropdown(
    ctx: AppContext,
    field_name: str,
    value: str,
    options: list[tuple[str, str]],
    width: int,
) -> ui.Control:
    return ui.Dropdown(
        value=value,
        width=width,
        dense=True,
        text_size=FS["small"],
        text_style=ui.TextStyle(size=FS["small"], color=TEXT),
        # 无边框 + 透明底：筛选是「可选修饰」，不该和搜索框抢注意力。
        # 也刻意不放 leading_icon：M3 下拉的前导图标会吃掉 ~40px，窄工具栏里
        # 直接导致选中文本被裁成一个字（实测「全部」只剩「全」）。
        filled=False,
        border=ui.NoInputBorder(),
        border_radius=radius_all(RAD["md"]),
        content_padding=ui.Padding(SP["2"], 0, SP["1"], 0),
        options=[ui.DropdownOption(key=k, text=v) for k, v in options],
        on_select=lambda e: ctx.search.on_filter(field_name, e.control.value),
        tooltip=_TOOLTIPS[field_name],
    )


def _icon_action(icon: str, tooltip: str, on_click) -> ui.Control:
    return ui.IconButton(
        icon=icon,
        icon_size=18,
        icon_color=TEXT_SUB,
        tooltip=tooltip,
        on_click=on_click,
    )


def _search_field_key(state: AppState) -> str:
    """搜索框的 diff key：焦点域切换时换 key 重挂载，用 autofocus 抢回焦点。"""
    return f"search-{state.focus_epoch}" if state.focus == Focus.SEARCH else "search"


def _search_field(ctx: AppContext, text: str) -> ui.TextField:
    """构造搜索框控件（只在需要新建时调用）。

    为什么 ``value`` 不给 ``state.query`` 做逐帧绑定（重要，改前先读）：

    搜索框一旦是「受控组件」，flet 的 diff 就会把上一次渲染写入的 ``value``
    与本次渲染的 ``value`` 作比较，不等就下发 replace。而中文输入法组合期间，
    客户端的文本（含 preedit 拼音）**领先于** Python 侧的 ``state.query``：
    事件还在路上、重绘已经执行，于是下发的是「过期文本」，Flutter 侧
    ``TextEditingController.text`` 被重置、composing region 被清空 —— 表现为
    拼音打一半被吃掉、候选框闪烁消失、已上屏的字被覆盖。

    因此这里改由 ``SearchBar`` 用 use_memo 长期持有同一个控件实例：打字期间
    依赖不变 → 复用实例 → flet 走「原地比较」，``_dirty`` 为空 → 零下发，
    IME 组合完全不受干扰。新建时机仅有：首次挂载、焦点域切换、正则开关切换、
    程序化写入（``state.query_set_seq`` 推进）。

    同理，**不要**在搜索框上加「按输入内容显隐」的后缀控件（例如清空按钮）：
    那会逼着 memo 依赖 ``state.query``，每次敲键都重建一次工具栏。清空走 Esc。
    """
    state = ctx.state
    return ui.TextField(
        value=text,
        hint_text=(
            r"正则模式：输入正则表达式匹配文件名，如 ^report.*\.xlsx$"
            if state.use_regex
            else "搜索文件名 · 支持 ext: / content: / 正则"
        ),
        expand=True,
        dense=True,
        text_size=FS["subtitle"],
        filled=True,
        fill_color=SURFACE,
        prefix_icon=ui.Icon(ui.Icons.SEARCH, size=18, color=TEXT_SUB),
        border=field_border(RAD["lg"]),
        content_padding=ui.Padding(0, SP["2"], SP["3"], SP["2"]),
        ignore_up_down_keys=True,
        autofocus=state.focus == Focus.SEARCH,
        # 唤回窗口时全选已有内容（一次性，输入即可覆盖旧查询）
        selection=(
            ui.TextSelection(base_offset=0, extent_offset=len(text))
            if ctx.services.select_on_focus and text
            else None
        ),
        key=_search_field_key(state),
        on_change=lambda e: ctx.search.on_query_changed(e.control.value),
        on_submit=lambda e: asyncio.create_task(ctx.search.submit()),
        on_focus=lambda e: ctx.selection.on_search_focused(),
    )


@ui.component
def SearchBar(ctx: AppContext):
    state = ctx.state
    # 已消费到的程序化写入序号（ref 的读写不触发重绘）
    seen = ui.use_ref(lambda: state.query_set_seq)

    def _field_text() -> str:
        """决定这次新建搜索框时写入的文本。"""
        if state.query_set_seq != seen.current:
            # 程序化写入（Esc 清空 / 应用书签 / 启动回填）：显式下发一次
            seen.current = state.query_set_seq
            return state.query_set
        # 其余重建（焦点域切换 / 正则开关）：沿用当前查询串。此刻用户已停手，
        # state.query 与输入框文本一致，不会吃掉正在输入的字符。
        return state.query

    search_field = ui.use_memo(
        lambda: _search_field(ctx, _field_text()),
        # 依赖刻意不含 state.query / state.results / state.searching：
        # 打字与结果更新都不应让搜索框控件重建或被下发属性。
        [state.use_regex, state.focus, state.focus_epoch, state.query_set_seq],
    )

    def _build() -> ui.Control:
        return ui.Container(
            padding=ui.Padding(SP["3"], SP["2"], SP["3"], SP["2"]),
            bgcolor=PANEL,
            border=bottom_border(),
            content=ui.Row(
                spacing=SP["2"],
                vertical_alignment=ui.CrossAxisAlignment.CENTER,
                controls=[
                    search_field,
                    _regex_toggle(ctx),
                    _divider(),
                    _dropdown(ctx, "category", state.category, CATEGORIES, 124),
                    _dropdown(ctx, "time", state.time_range, TIME_RANGES, 120),
                    _dropdown(ctx, "size", state.size_range, SIZE_RANGES, 124),
                    _divider(),
                    _icon_action(
                        ui.Icons.BOOKMARK_ADD,
                        "保存当前搜索条件为书签",
                        lambda e: ctx.bookmarks.open_save_dialog(),
                    ),
                    _icon_action(
                        ui.Icons.REFRESH,
                        "刷新 (F5)",
                        lambda e: asyncio.create_task(
                            ctx.search.run_search(keep_selection=True)
                        ),
                    ),
                    _icon_action(
                        ui.Icons.SETTINGS,
                        "设置全局热键",
                        lambda e: ctx.settings.open_hotkey(),
                    ),
                ],
            ),
        )

    # 整树记忆化：搜索栏只由「搜索框实例 + 正则开关 + 三个筛选值」决定外观，
    # 打字、结果更新、选中变化都不该让它重建（flet 的 observable 是对象级通知，
    # 不做这层缓存的话每个 state 字段变化都会把整条工具栏重建一遍）。
    return ui.use_memo(
        _build,
        [
            search_field,
            state.use_regex,
            state.category,
            state.time_range,
            state.size_range,
        ],
    )
