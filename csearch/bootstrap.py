"""应用启动装配：页面/窗口配置、全局事件接线，然后渲染根组件。"""

from __future__ import annotations

import asyncio
import os

import flet as ft

from csearch import store
from csearch.constants import (
    APP_TITLE,
    FONT_ASSET,
    FONT_FAMILY,
    ICON_ASSET,
)
from csearch.controller import on_keyboard, on_window_event
from csearch.state import services
from csearch.ui.app import App

# assets 目录（包的上一级）
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def _configure_page(page: ft.Page, cfg) -> None:
    """全局样式与字体（无边框紧凑桌面风）。"""
    page.title = APP_TITLE
    page.padding = 0
    page.spacing = 0
    page.bgcolor = "#F7F8FA"
    page.fonts = {FONT_FAMILY: FONT_ASSET}
    page.theme = ft.Theme(
        font_family=FONT_FAMILY,
        color_scheme_seed="#1A73E8",
        use_material3=True,
    )
    page.theme_mode = ft.ThemeMode.LIGHT

    geo = cfg.window
    page.window.title = APP_TITLE
    page.window.width, page.window.height = geo.width, geo.height
    page.window.min_width, page.window.min_height = 760, 480
    if geo.left is not None and geo.top is not None:
        page.window.left, page.window.top = geo.left, geo.top
    else:
        page.window.center()
    page.window.prevent_close = True  # 点 X 拦截为隐藏到托盘
    page.window.visible = not cfg.start_hidden
    try:
        page.window.icon = ICON_ASSET
    except Exception:  # noqa: BLE001
        pass


async def boot(page: ft.Page) -> None:
    """Flet 入口：配置页面、接线全局事件、渲染根组件。"""
    cfg = store.load_config()
    _configure_page(page, cfg)

    # 全局键盘事件（页面级快捷键；state 由根组件挂载后写入 services）
    page.on_keyboard_event = lambda e: asyncio.create_task(
        on_keyboard(services.state, e)
    )
    # 窗口事件：关闭→托盘 / 唤回焦点 / 缩放列适配 / 几何记忆
    # 注意：flet 1.0 的窗口事件挂在 Window.on_event 上，Page 并没有 on_window_event 字段。
    # 写成 page.on_window_event 只是个普通属性，flet 永远不读——配合 prevent_close=True
    # 会表现为「点 X 毫无反应且关不掉」。
    page.window.on_event = lambda e: on_window_event(services.state, e)

    page.render(App)  # 1.0 中 render 为同步挂载


def run() -> None:
    # Flet 1.0 默认 AppView.FLET_APP 即桌面原生窗口
    ft.run(boot, assets_dir=_ASSETS_DIR)
