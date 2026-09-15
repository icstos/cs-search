"""根组件：单列布局（搜索行 → 结果/书签区 → 状态栏）+ 全局副作用。"""

from __future__ import annotations

import asyncio

import flet as ft

from csearch.controller import bridge_loop, init_app
from csearch.state import AppState, services
from csearch.ui.dialogs import dialogs
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

    return ft.Column(
        expand=True,
        spacing=0,
        controls=[
            SearchBar(state),
            Results(state),
            StatusBar(state),
        ],
    )
