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


def _subscribe_ui_state(ctx: AppContext) -> None:
    """把根组件挂到 ``ctx.state`` 的变更通知上（**全局重绘的总开关**）。

    为什么必须显式订阅（flet 1.0 机制，改前先读）：
    flet 只会为「**作为组件参数传入的** ``Observable``」自动建立订阅
    （见 ``Component._subscribe_observable_args``：它只遍历 ``args`` / ``kwargs``
    本身，不看参数内部的字段）。MVVM 重构后各组件拿到的是 ``AppContext``
    ——一个持有 state 的**普通 dataclass**，它本身不是 ``Observable``，
    于是整棵组件树没有任何人订阅 ``ctx.state``。

    表现：``state`` 的任意字段变化都只是改了个 Python 属性，不触发任何重绘。
    搜索流程其实一直在正常跑（结果已写进 ``state.results``），但界面冻结，
    于是表现为「输入框能打字、搜索也发出去了，**结果列表却永远不更新**」。

    这里借 ``ft.use_state`` 完成订阅：它在初值是 ``Observable`` 时会自动为当前
    组件挂上订阅（``StateHook.subscription``），返回的 setter 用不上、丢弃即可，
    状态本身仍是 ``ctx.state`` 这一个单例。

    只需在根组件订阅一次：子组件每次都随父组件重渲染而重跑 body，且各自已有
    ``use_memo`` 兜底，无需逐个订阅（这与重构前的行为一致——那时
    ``ft.use_state(lambda: AppState())`` 返回的是 observable 的 state 本身，
    根组件因此自动订阅）。
    """
    ft.use_state(ctx.state)


@ft.component
def App():
    ctx, _ = ft.use_state(lambda: AppContext.build())
    _subscribe_ui_state(ctx)
    set_current(ctx)  # 供页面级事件（键盘 / 窗口）在组件树之外回调
    # 注册滚动端口：viewmodel 只持有 ScrollTarget 抽象，不接触 ListView 控件
    ctx.services.scroll = ListViewScroller(results_list_ref)

    tasks: dict[str, asyncio.Task] = {}

    def _setup():
        tasks["init"] = asyncio.create_task(ctx.session.init())
        tasks["bridge"] = asyncio.create_task(ctx.session.bridge_loop())
        # 外部文件变更的实时同步常驻任务（窗口可见时才探测，隐藏时自动让位）
        tasks["sync"] = asyncio.create_task(ctx.search.sync_loop())

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
