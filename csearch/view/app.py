"""根组件：单列布局（搜索行 → 结果/书签区 → 状态栏）+ 全局副作用。

本层零业务逻辑：构建 MVVM 上下文、注册 view 侧运行时端口、挂载对话框与菜单层。
"""

from __future__ import annotations

import asyncio

import flet as ft

from csearch.view.dialogs import dialogs
from csearch.view.menu import menu_layer
from csearch.view.results import Results
from csearch.view.scroller import ListViewScroller, results_list_ref
from csearch.view.searchbar import SearchBar
from csearch.view.statusbar import StatusBar
from csearch.viewmodel.context import AppContext, set_current


@ft.component
def App():
    ctx, _ = ft.use_state(lambda: AppContext.build())
    set_current(ctx)  # 供页面级事件（键盘 / 窗口）在组件树之外回调
    # 注册滚动端口：viewmodel 只持有 ScrollTarget 抽象，不接触 ListView 控件
    ctx.services.scroll = ListViewScroller(results_list_ref)

    tasks: dict[str, asyncio.Task] = {}

    def _setup():
        tasks["init"] = asyncio.create_task(ctx.session.init())
        tasks["bridge"] = asyncio.create_task(ctx.session.bridge_loop())

    def _cleanup():
        for task in tasks.values():
            task.cancel()

    ft.use_effect(_setup, [], _cleanup)
    dialogs(ctx)

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
                    SearchBar(ctx),
                    Results(ctx),
                    StatusBar(ctx),
                ],
            ),
            *menu_layer(ctx),
        ],
    )
