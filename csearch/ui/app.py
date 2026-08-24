"""根组件：布局装配 + 全局副作用（初始化 / 事件桥 / 对话框挂载）。"""

from __future__ import annotations

import asyncio

import flet as ft

from csearch import logic
from csearch.state import AppState, services
from csearch.ui.dialogs import dialogs
from csearch.ui.results import Results
from csearch.ui.searchbar import SearchBar
from csearch.ui.sidebar import Sidebar
from csearch.ui.statusbar import StatusBar


@ft.component
def App():
    page = ft.context.page
    state, _ = ft.use_state(lambda: AppState())
    services.state = state

    tasks: dict[str, asyncio.Task] = {}

    def _setup():
        tasks["init"] = asyncio.create_task(logic.init_app(state))
        tasks["bridge"] = asyncio.create_task(logic.bridge_loop(state))
        return None

    def _cleanup():
        for task in tasks.values():
            task.cancel()

    ft.use_effect(_setup, [], _cleanup)
    dialogs(state)

    return ft.Row(
        expand=True,
        spacing=0,
        controls=[
            Sidebar(state),
            ft.Container(width=1, bgcolor="#E4E7ED"),
            ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    SearchBar(state),
                    Results(state),
                    StatusBar(state),
                ],
            ),
        ],
    )
