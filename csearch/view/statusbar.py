"""底部状态栏：左侧结果/选中统计，右侧引擎状态、耗时与明暗切换。

外观交给 cs-ui 的 ``ui.StatusBar``（高度 / 底色 / 顶边线 / 状态点 / 贴右动作区
都在组件里定死），本文件只负责**文案与语气**——「什么时候显示什么、是什么颜色」
是业务判断，不该沉到组件里。

状态用「小圆点 + 文字」表达（点给颜色、字给信息），比整行染色更克制：
一整条彩色状态栏在长会话里会持续抢注意力。
"""

from __future__ import annotations

import ui

from csearch.models.constants import MAX_LOADED
from csearch.view.theme import FS, FW, ICON, danger
from csearch.viewmodel.context import AppContext
from csearch.viewmodel.state import AppState


def _left_text(state: AppState) -> str:
    """左侧统计文案。"""
    if state.query.strip():
        loaded = len(state.results)
        if loaded < state.total:
            base = f"已加载 {loaded} / {state.total} 条"
        else:
            base = f"共 {state.total} 条结果"
        if state.total >= MAX_LOADED:
            base += f"（最多加载 {MAX_LOADED} 条）"
        if state.selected:
            base += f"，已选中 {len(state.selected)} 项"
        return base
    return f"书签 {len(state.bookmarks)} 个 · 单击应用"


def _right_text(state: AppState) -> str:
    """右侧状态文案。"""
    if not state.engine_ok:
        return "Everything 未运行"
    if state.searching:
        return "搜索中…"
    if state.query.strip():
        return f"耗时 {state.elapsed_ms:.0f} ms"
    if state.engine_version:
        return f"Everything {state.engine_version} 就绪"
    return "就绪"


def _tone(state: AppState) -> str:
    """状态点的语气：故障 / 进行中 / 正常 / 空闲。"""
    if not state.engine_ok:
        return "danger"
    if state.searching:
        return "warning"
    if state.query.strip() or state.engine_version:
        return "success"
    return "neutral"


def _theme_button(ctx: AppContext) -> ui.Control:
    """明暗切换：图标显示「点了会变成什么」，tooltip 说清当前状态。"""
    is_dark = ui.core.theme.current_mode() == "dark"
    return ui.IconButton(
        icon=ui.Icons.LIGHT_MODE if is_dark else ui.Icons.DARK_MODE,
        icon_size=ICON["sm"],
        icon_color=ui.Colors.ON_SURFACE_VARIANT,
        tooltip="切换到浅色主题" if is_dark else "切换到深色主题",
        on_click=lambda e: ctx.settings.toggle_theme(),
    )


@ui.component
def StatusBar(ctx: AppContext):
    state = ctx.state
    # 状态栏只由这几段派生值决定外观：直接以它们为依赖做整树记忆化，
    # 免去「任何 state 字段变化都重建一遍状态栏」的固定开销。
    left = _left_text(state)
    right = _right_text(state)
    tone = _tone(state)
    # 明暗切换要换按钮图标（☀/🌙），所以主题模式必须进依赖表，否则切过去图标不动。
    mode = state.theme_mode

    def _status_text() -> str | ui.Control:
        """故障态用危险色加粗：这是唯一需要「文字也跟着变色」的场合。

        其余状态都交给中性灰 —— 状态点已经说明了一切，再染文字就吵了。
        """
        if tone != "danger":
            return right
        return ui.Text(
            right,
            size=FS["small"],
            color=danger(),
            weight=FW["medium"],
            no_wrap=True,
        )

    def _build() -> ui.Control:
        return ui.StatusBar(
            summary=left,
            status=_status_text(),
            tone=tone,
            actions=[_theme_button(ctx)],
        )

    return ui.use_memo(_build, [left, right, tone, mode])
