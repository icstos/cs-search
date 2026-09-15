"""底部状态栏：左侧结果/选中统计，右侧引擎状态与耗时。"""

from __future__ import annotations

import flet as ft

from csearch.constants import MAX_LOADED
from csearch.state import AppState
from csearch.ui.theme import C, sym_padding, top_border


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
    return f"书签 {len(state.bookmarks)} 个（单击应用）"


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


def _right_color(state: AppState) -> str:
    if not state.engine_ok:
        return C.DANGER
    if state.searching:
        return C.WARNING
    if state.query.strip() or state.engine_version:
        return C.SUCCESS
    return C.TEXT_HINT


@ft.component
def StatusBar(state: AppState):
    return ft.Container(
        height=28,
        bgcolor=C.SURFACE,
        border=top_border(),
        padding=sym_padding(12, 6),
        content=ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(_left_text(state), size=12, color=C.TEXT_SUB, expand=True),
                ft.Text(_right_text(state), size=12, color=_right_color(state)),
            ],
        ),
    )
