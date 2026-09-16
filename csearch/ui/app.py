"""根组件：单列布局（搜索行 → 结果/书签区 → 状态栏）+ 全局副作用。"""

from __future__ import annotations

import asyncio

import flet as ft

from csearch.controller import bridge_loop, init_app
from csearch.state import AppState, services
from csearch.ui.dialogs import dialogs
from csearch.ui.menu import menu_layer
from csearch.ui.results import Results
from csearch.ui.searchbar import SearchBar
from csearch.ui.statusbar import StatusBar


@ft.component
def App():
    state, _ = ft.use_state(lambda: AppState())
    services.state = state

    tasks: dict[str, asyncio.Task] = {}

    def _setup():
        tasks["init"] = asyncio.create_task(init_app(state))
        tasks["bridge"] = asyncio.create_task(bridge_loop(state))

    def _cleanup():
        for task in tasks.values():
            task.cancel()

    ft.use_effect(_setup, [], _cleanup)
    dialogs(state)

    # 根 Stack：内容列 + 右键菜单覆盖层（遮罩/面板按指针坐标绝对定位）。
    # fit=EXPAND 是必须的：松约束下内容列会按内容收缩，右下的空白区点击会落空。
    return ft.Stack(
        expand=True,
        fit=ft.StackFit.EXPAND,
        controls=[
            ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    SearchBar(state),
                    Results(state),
                    StatusBar(state),
                ],
            ),
            *menu_layer(state),
        ],
    )
