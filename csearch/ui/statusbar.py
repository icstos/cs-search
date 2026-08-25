"""底部状态栏：命中总数 / 已加载 / 耗时 / Everything 索引状态。"""

from __future__ import annotations

import flet as ft

from csearch.state import AppState


@ft.component
def StatusBar(state: AppState):
    left = (
        ft.Text("输入关键词开始搜索", size=12, color="#9AA0A6")
        if not state.query.strip() else
        ft.Text(f"搜索中… 已找到 {state.total:,} 项", size=12, color="#5F6368")
        if state.searching else
        ft.Text(
            f"{state.total:,} 个结果"
            + (f"（已加载 {len(state.results):,}）" if len(state.results) < state.total else "")
            + f" · {state.elapsed_ms:.0f} ms",
            size=12, color="#5F6368",
        )
    )
    index_status = (
        ft.Text(f"Everything 未运行 {state.engine_version}".strip(), size=12, color="#D93025")
        if not state.engine_ok else
        ft.Text(f"索引就绪 {state.engine_version}".strip(), size=12, color="#188038")
        if state.index_ready else
        ft.Text("索引加载中…", size=12, color="#F9AB00")
    )
    return ft.Container(
        padding=ft.Padding(12, 6, 12, 6),
        bgcolor="#FFFFFF",
        border=ft.Border(top=ft.BorderSide(1, "#E4E7ED")),
        content=ft.Row(spacing=12, controls=[left, ft.Container(expand=True), index_status]),
    )
