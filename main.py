"""CSearch 入口：窗口初始化（几何记忆 / 托盘关闭语义 / 事件注册）+ 声明式渲染。

运行：python main.py
"""

from __future__ import annotations

import os
import sys

import flet as ft

# 引导：嵌入式/便携 Python 可能不自动把脚本目录加入 sys.path，这里显式补上
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from csearch.controller import on_page_keyboard, on_window_event
from csearch.state import services
from csearch.ui.app import App

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


async def main(page: ft.Page) -> None:
    cfg = services.config
    geo = cfg.get_window()

    page.title = "CSearch - 极速文件搜索"
    page.bgcolor = "#F7F8FA"
    page.padding = 0
    page.spacing = 0

    # 窗口：记忆尺寸/位置，限制最小尺寸（适配高 DPI 缩放）
    page.window.width = geo.width
    page.window.height = geo.height
    if geo.left is not None:
        page.window.left = geo.left
    if geo.top is not None:
        page.window.top = geo.top
    page.window.min_width = 760
    page.window.min_height = 480
    page.window.maximized = geo.maximized
    page.window.prevent_close = True  # 关闭窗口 → 最小化到系统托盘

    ico = os.path.join(ASSETS_DIR, "icon.ico")
    if os.path.isfile(ico):
        try:
            page.window.icon = ico
        except Exception:  # noqa: BLE001
            pass

    if cfg.get_start_hidden():
        page.window.visible = False  # 后台常驻启动（托盘唤起）

    # 页面级事件（一次性副作用注册；state 由 App 挂载后注入 services.state）
    page.on_keyboard_event = lambda e: on_page_keyboard(page, services.state, e)
    page.window.on_event = lambda e: on_window_event(page, services.state, e)

    page.render(App)


if __name__ == "__main__":
    ft.run(main, view=ft.AppView.FLET_APP)
