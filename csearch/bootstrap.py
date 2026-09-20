"""应用启动装配：轻量入口 + 后台预热 + 首帧占位。

启动时序（依据 flet 1.0.0 内部实现，改前先读）：

    import csearch.bootstrap        <- 本模块（此刻仅导入 flet / constants / store）
    ft.run(boot)
      └─ asyncio.run(run_async(...))
           └─ FletSocketServer.start()      <- 这里才真正拉起桌面客户端 flet.exe
                └─ 客户端连上后才回调 boot   <- 首个界面在此渲染

关键结论：**模块导入全部发生在桌面客户端进程启动之前**。因此本模块只做两件事：

1. 导入期立刻用守护线程开始预热重依赖（``preload.start()``），让
   「导入 sqlmodel / everytools / pystray…」与「拉起并初始化客户端」并行；
2. ``boot`` 里只做页面配置与最小接线，先渲染一个轻量占位帧，等预热结束后再挂载
   真正的根组件 ``csearch.ui.app.App``。

相比于把重依赖留在模块顶层（旧写法约 1.6s 全部串行在客户端启动之前），这样可以把
其中约 0.6~0.9s 藏到客户端启动的阴影里。
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import flet as ft

from csearch import preload, store
from csearch.constants import (
    APP_TITLE,
    FONT_ASSET,
    FONT_FAMILY,
    ICON_ASSET,
)

# assets 目录（包的上一级）
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

# 模块导入即开始预热：此刻 ft.run 尚未调用，客户端也尚未被拉起，两者正好并行
preload.start()


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


# --------------------------------------------------------------------- 首帧占位
@ft.component
def _Splash():
    """预热期间的首帧：极轻量，只为让窗口立刻有内容可画。"""
    return ft.Container(
        expand=True,
        bgcolor="#F7F8FA",
        alignment=ft.Alignment(0, 0),
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
            controls=[
                ft.ProgressRing(width=22, height=22, stroke_width=2.4),
                ft.Text("正在启动 CSearch…", size=13, color="#5F6368"),
            ],
        ),
    )


@ft.component
def _Root():
    """根组件：预热未完成显示占位帧，完成后无缝切到真正的 App。"""
    ready, set_ready = ft.use_state(preload.done())

    if not ready:

        def _watch():
            async def _wait() -> None:
                # 在后台线程等待，避免阻塞事件循环（预热本身也是线程里跑的）
                await asyncio.to_thread(preload.wait)
                set_ready(True)  # 无论成功失败都放行，错误留给 App 自己呈现

            task = asyncio.create_task(_wait())
            return lambda: task.cancel()

        ft.use_effect(_watch, [])
        return _Splash()

    from csearch.ui.app import App  # 已预热，此处近乎零成本

    return App()


# --------------------------------------------------------------------- 全局接线
def _deferred_keyboard(e: Any) -> None:
    """页面级快捷键：首次触发时再导入控制器（预热早已完成，代价可忽略）。"""
    from csearch.controller import on_keyboard
    from csearch.state import services

    asyncio.create_task(on_keyboard(services.state, e))


def _deferred_window_event(e: Any) -> None:
    """窗口事件：关闭→托盘 / 唤回焦点 / 缩放列适配 / 几何记忆。

    注意：flet 1.0 的窗口事件挂在 ``Window.on_event`` 上，Page 并没有
    ``on_window_event`` 字段。写成 ``page.on_window_event`` 只是个普通属性，flet
    永远不读——配合 ``prevent_close=True`` 会表现为「点 X 毫无反应且关不掉」。
    """
    from csearch.controller import on_window_event
    from csearch.state import services

    on_window_event(services.state, e)


async def boot(page: ft.Page) -> None:
    """Flet 入口：配置页面、接线全局事件、渲染根组件。"""
    cfg = store.load_config()
    _configure_page(page, cfg)

    page.on_keyboard_event = _deferred_keyboard
    page.window.on_event = _deferred_window_event

    page.render(_Root)  # 1.0 中 render 为同步挂载


def run() -> None:
    # Flet 1.0 默认 AppView.FLET_APP 即桌面原生窗口
    ft.run(boot, assets_dir=_ASSETS_DIR)
