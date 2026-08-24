"""状态栏：命中总数 / 已加载 / 耗时 / Everything 索引状态。"""

from __future__ import annotations

import flet as ft

from csearch.state import AppState


@ft.component
def StatusBar(state: AppState):
    if state.searching:
        left = ft.Text(f"搜索中… 已找到 {state.total:,} 项", size=12, color="#5F6368")
    else:
        left = ft.Text(
            f"{state.total:,} 个结果"
            + (f"（已加载 {state.loaded:,}）" if state.loaded < state.total else "")
            + f" · {state.elapsed_ms:.0f} ms",
            size=12,
            color="#5F6368",
        )

    # 索引状态
    if not state.engine_ok:
        idx = ft.Text(f"Everything 未运行 {state.engine_version}".strip(), size=12, color="#D93025")
    elif state.index_ready:
        idx = ft.Text(f"索引就绪 {state.engine_version}".strip(), size=12, color="#188038")
    else:
        idx = ft.Text("索引加载中…", size=12, color="#F9AB00")

    return ft.Container(
        padding=ft.Padding(12, 6, 12, 6),
        bgcolor="#FFFFFF",
        border=ft.Border(top=ft.BorderSide(1, "#E4E7ED")),
        content=ft.Row(
            spacing=12,
            controls=[
                left,
                ft.Container(expand=True),
                idx,
            ],
        ),
    )
