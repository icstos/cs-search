"""根组件：布局装配 + 全局副作用（初始化 / 事件桥 / 对话框）。"""

from __future__ import annotations

import asyncio

import flet as ft

from csearch import controller
from csearch.state import AppState, services
from csearch.ui.dialogs import bookmark_dialog, delete_dialog, hotkey_dialog, size_dialog
from csearch.ui.result_list import ResultsView
from csearch.ui.search_bar import SearchBar
from csearch.ui.sidebar import Sidebar
from csearch.ui.status_bar import StatusBar


@ft.component
def App():
    page = ft.context.page
    state, _ = ft.use_state(lambda: AppState())

    # 挂载副作用：初始化后台服务 + 启动事件桥消费循环
    tasks: dict[str, asyncio.Task] = {}

    def _setup():
        services.state = state
        tasks["init"] = asyncio.create_task(controller.init_app(page, state))
        tasks["bridge"] = asyncio.create_task(controller.bridge_loop(state, page))
        return None

    def _cleanup():
        for t in tasks.values():
            t.cancel()

    ft.use_effect(_setup, [], _cleanup)

    # 声明式对话框（None = 隐藏）
    ft.use_dialog(delete_dialog(state) if state.dlg_delete else None)
    ft.use_dialog(bookmark_dialog(state) if state.dlg_bookmark else None)
    ft.use_dialog(hotkey_dialog(state) if state.dlg_hotkey else None)
    ft.use_dialog(size_dialog(state) if state.dlg_size else None)

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
                    ResultsView(state),
                    StatusBar(state),
                ],
            ),
        ],
    )
