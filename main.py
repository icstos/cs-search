"""CSearch 入口：窗口配置 + 页面事件注册 + 声明式渲染。

运行：python main.py
"""

from __future__ import annotations

import os

import flet as ft

# import logging

# logging.basicConfig(level=logging.DEBUG)

from csearch import logic, store
from csearch.state import services
from csearch.ui.app import App

_ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.ico")


async def main(page: ft.Page) -> None:
    cfg = store.load_config()
    w = cfg.window

    page.title = "CSearch - 极速文件搜索"
    page.bgcolor = "#F7F8FA"
    page.padding = 0
    page.spacing = 0
    page.window.width, page.window.height = w.width, w.height
    if w.left is not None:
        page.window.left = w.left
    if w.top is not None:
        page.window.top = w.top
    page.window.min_width, page.window.min_height = 900, 520
    page.window.maximized = w.maximized
    page.window.prevent_close = True  # 关闭 → 最小化到托盘
    if os.path.isfile(_ICON):
        try:
            page.window.icon = _ICON
        except Exception:  # noqa: BLE001
            pass
    if cfg.start_hidden:
        page.window.visible = False

    page.on_keyboard_event = lambda e: logic.on_keyboard(services.state, e)
    page.window.on_event = lambda e: logic.on_window_event(services.state, e)
    page.render(App)


if __name__ == "__main__":
    ft.run(main, view=ft.AppView.FLET_APP)
