"""会话编排：应用初始化（服务装配 / 引擎检测 / 托盘热键 / 启动即搜）与桥事件循环。"""

from __future__ import annotations

import asyncio
import os

from csearch import history, store
from csearch.constants import APP_TITLE
from csearch.controller.search import (
    run_search,
    scroll_results,
    set_query,
    silent_refresh,
)
from csearch.controller.window import (
    ensure_on_screen_later,
    hide_to_tray,
    quit_app,
    show_window,
    toggle_window,
)
from csearch.state import AppState, services
from csearch.tray_manager import TrayManager
from csearch.wheel_bridge import WheelBridge


def _start_wheel_bridge() -> None:
    """滚轮桥（后台线程内调用）。

    部分环境不把 WM_MOUSEWHEEL 投递给 Flutter，用低级钩子兜底。``start()`` 内部要
    等钩子安装结果（超时上限 3s），且会去拉 ``FindWindowW``——必须放在线程里，
    否则窗口刚出现时事件循环会被冻住数秒。
    """
    wheel = WheelBridge(lambda d: services.bridge.emit("wheel", delta=d))
    services.wheel = wheel if wheel.start() else None


def _start_tray_and_db() -> None:
    """托盘 + 全局热键 + 运行历史建表（后台线程内调用，彼此无依赖）。"""
    history.init_db()
    try:
        tray = TrayManager(
            title=APP_TITLE,
            hotkey=store.load_config().hotkey,
            # 热键固定激活窗口并置顶（不切换隐藏）；托盘左键单击才切换
            on_hotkey=lambda: services.bridge.emit("show"),
            on_toggle=lambda: services.bridge.emit("toggle"),
            on_show=lambda: services.bridge.emit("show"),
            on_hide=lambda: services.bridge.emit("hide"),
            on_quit=lambda: services.bridge.emit("quit"),
        )
        # start() 返回 False = 托盘与热键均不可用：置空后 hide_to_tray 会降级为真退出
        services.tray = tray if tray.start() else None
    except Exception:  # noqa: BLE001
        services.tray = None


async def init_app(state: AppState) -> None:
    """组件挂载后的一次性初始化（幂等性由调用方保证）。"""
    # 延迟校验窗口位置：多显示器布局变化时保存的坐标可能失效
    asyncio.create_task(ensure_on_screen_later())

    # 三件互不依赖的启动工作并发执行：滚轮桥 / 托盘热键+建表 / 引擎状态检测。
    # 它们各自都可能阻塞若干秒，全部走线程池，事件循环只负责等结果。
    status, _, _ = await asyncio.gather(
        asyncio.to_thread(services.engine.check_status),
        asyncio.to_thread(_start_wheel_bridge),
        asyncio.to_thread(_start_tray_and_db),
    )
    ok, msg, db = status
    state.engine_ok, state.engine_msg, state.index_ready = ok, msg, db
    state.engine_version = services.engine.version
    state.bookmarks = store.load_bookmarks()

    # 优先事件驱动通知；官方 1.5 SDK DLL 缺失时降级为 5s 签名轮询
    if not services.engine.notify_registered:
        services.engine.start_change_monitor(
            lambda: services.bridge.emit("index_changed")
        )

    # 启动即搜索（环境变量 CSEARCH_QUERY；默认空 = 展示书签面板）
    init_query = os.environ.get("CSEARCH_QUERY", "").strip()
    if init_query:
        set_query(state, init_query, run=False)  # 程序化回填搜索框
    await run_search(state)


async def bridge_loop(state: AppState) -> None:
    """后台线程事件 → 主线程 GUI 操作的统一分发循环。"""
    while True:
        ev = await services.bridge.next()
        match ev["type"]:
            case "toggle":
                await toggle_window(state)
            case "show":
                await show_window(state)
            case "hide":
                hide_to_tray(state)
            case "quit":
                await quit_app(state)
                return
            case "wheel":
                await scroll_results(state, int(ev.get("delta", 0) or 0))
            case "index_changed":
                await silent_refresh(state)
