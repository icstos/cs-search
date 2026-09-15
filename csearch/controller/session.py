"""会话编排：应用初始化（服务装配 / 引擎检测 / 托盘热键 / 启动即搜）与桥事件循环。"""

from __future__ import annotations

import asyncio
import os

from csearch import history, store
from csearch.constants import APP_TITLE
from csearch.controller.search import run_search, scroll_results, silent_refresh
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


async def init_app(state: AppState) -> None:
    """组件挂载后的一次性初始化（幂等性由调用方保证）。"""
    # 延迟校验窗口位置：多显示器布局变化时保存的坐标可能失效
    asyncio.create_task(ensure_on_screen_later())

    # 滚轮桥：部分环境不投递 WM_MOUSEWHEEL 给 Flutter，用低级钩子兜底
    services.wheel = WheelBridge(lambda d: services.bridge.emit("wheel", delta=d))
    if not services.wheel.start():
        services.wheel = None

    await asyncio.to_thread(history.init_db)

    ok, msg, db = await asyncio.to_thread(services.engine.check_status)
    state.engine_ok, state.engine_msg, state.index_ready = ok, msg, db
    state.engine_version = services.engine.version
    state.bookmarks = store.load_bookmarks()

    try:
        services.tray = TrayManager(
            title=APP_TITLE,
            hotkey=store.load_config().hotkey,
            # 热键固定激活窗口并置顶（不切换隐藏）；托盘左键单击才切换
            on_hotkey=lambda: services.bridge.emit("show"),
            on_toggle=lambda: services.bridge.emit("toggle"),
            on_show=lambda: services.bridge.emit("show"),
            on_hide=lambda: services.bridge.emit("hide"),
            on_quit=lambda: services.bridge.emit("quit"),
        )
        services.tray.start()
    except Exception:  # noqa: BLE001
        services.tray = None

    # 优先事件驱动通知；官方 1.5 SDK DLL 缺失时降级为 5s 签名轮询
    if not services.engine.notify_registered:
        services.engine.start_change_monitor(
            lambda: services.bridge.emit("index_changed")
        )

    # 启动即搜索（环境变量 CSEARCH_QUERY；默认空 = 展示书签面板）
    init_query = os.environ.get("CSEARCH_QUERY", "").strip()
    if init_query:
        state.query = init_query
        if services.wheel is not None:
            services.wheel.swallow = True
    await run_search(state)


async def bridge_loop(state: AppState) -> None:
    """后台线程事件 → 主线程 GUI 操作的统一分发循环。"""
    while True:
        ev = await services.bridge.next()
        if ev is None:
            continue
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
