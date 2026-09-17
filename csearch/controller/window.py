"""窗口管理：托盘显隐 / 唤回抢焦 / 几何记忆 / 窗口事件分发 / 退出。"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import flet as ft

from csearch import store
from csearch.constants import APP_TITLE
from csearch.controller.columns import adapt_columns
from csearch.controller.common import focus_search, page
from csearch.platform import ensure_window_on_screen, force_foreground_by_title
from csearch.state import AppState, services

# 几何保存去抖任务
_geo_task: asyncio.Task | None = None
_MIN_WIN_W, _MIN_WIN_H = 760, 480


async def show_window(state: AppState) -> None:
    """唤回窗口：取消最小化、置顶、纠正屏幕外位置并抢回键盘焦点。"""
    p = page()
    try:
        p.window.visible, p.window.minimized = True, False
        p.update()
        ensure_window_on_screen()  # 多显示器布局变化后保存的坐标可能失效
        await p.window.to_front()  # 协程必须 await，否则不置顶且产生 RuntimeWarning
    except Exception:  # noqa: BLE001
        pass
    force_foreground_by_title(p.title)  # Windows 前台锁定兜底
    focus_search(state)
    # 唤回时全选搜索框已有内容（一次性标记，SearchBar 重挂载时下发 selection）
    if state.query:
        services.select_on_focus = True


def hide_to_tray(state: AppState) -> None:
    """隐藏到托盘，首次弹一次气泡提示。

    托盘图标与全局热键都不可用时，隐藏窗口 = 应用变成唤不回来的后台进程；
    此时降级为真退出，避免「点 X 后既看不见也关不掉」。
    """
    tray = services.tray
    if tray is None or not tray.running:
        asyncio.create_task(quit_app(state))
        return
    try:
        p = page()
        p.window.visible = False
        p.update()
    except Exception:  # noqa: BLE001
        pass
    if not state.balloon_shown:
        state.balloon_shown = True
        tray.notify("已最小化到系统托盘，全局热键可再次唤起", APP_TITLE)


async def toggle_window(state: AppState) -> None:
    if page().window.visible:
        hide_to_tray(state)
    else:
        await show_window(state)


def _save_geometry() -> None:
    """把当前窗口几何写回配置（夹一道最小尺寸下限）。"""
    p = page()
    try:
        geo = store.load_config().window
        geo.width = max(_MIN_WIN_W, int(p.window.width or geo.width))
        geo.height = max(_MIN_WIN_H, int(p.window.height or geo.height))
        if p.window.left is not None:
            geo.left = int(p.window.left)
        if p.window.top is not None:
            geo.top = int(p.window.top)
        geo.maximized = bool(p.window.maximized)
        store.save_window(geo)
    except Exception:  # noqa: BLE001
        pass


async def _save_geometry_later() -> None:
    await asyncio.sleep(0.6)
    _save_geometry()


def on_window_event(state: AppState | None, e: Any) -> None:
    """窗口事件：关闭→托盘；显示/恢复→焦点回搜索框；缩放/移动→列适配 + 去抖存几何。"""
    global _geo_task
    if state is None:
        return
    # e.type 为 WindowEventType 枚举，直接按枚举匹配
    match getattr(e, "type", None):
        case ft.WindowEventType.CLOSE if not state.quitting:
            hide_to_tray(state)
        case ft.WindowEventType.SHOW:
            focus_search(state)
            if state.query:  # 与 show_window 幂等：保证最后一次重挂载仍带全选
                services.select_on_focus = True
        case ft.WindowEventType.RESTORE:
            focus_search(state)  # 任务栏/Alt+Tab 唤回同样抢回搜索框焦点
        case ft.WindowEventType.RESIZED | ft.WindowEventType.MOVED:
            adapt_columns(state)
            if _geo_task is not None:
                _geo_task.cancel()
            _geo_task = asyncio.create_task(_save_geometry_later())


async def ensure_on_screen_later() -> None:
    """启动延迟兜底：等客户端应用完保存的几何后再校验屏幕内位置。"""
    await asyncio.sleep(0.6)
    ensure_window_on_screen()


async def quit_app(state: AppState) -> None:
    """真正退出：停热键/托盘/滚轮/索引监听，再销毁窗口。"""
    if state.quitting:
        return
    state.quitting = True
    _save_geometry()
    # 退出顺序：滚轮桥 → 托盘（内部先停热键）→ 引擎监听 → 关窗
    if services.wheel is not None:
        services.wheel.stop()
        services.wheel = None
    if services.tray is not None:
        services.tray.stop()
        services.tray = None
    services.engine.stop_change_monitor()
    try:
        p = page()
        p.window.prevent_close = False
        await p.window.destroy()  # 协程必须 await
    except Exception:  # noqa: BLE001
        os._exit(0)
