"""组合根：装配 infra → service → viewmodel，配置页面，接线全局事件，启动应用。

分层落点（唯一允许同时"认识"所有层的地方）：

    infra 具体实现 ──注入──▶ service（只依赖 ports）──注入──▶ viewmodel ──▶ view

启动时序（依据 flet 1.0.3 内部实现，改前先读）：

    import csearch.bootstrap        <- 本模块（此刻仅导入 flet / preload / 常量）
    ui.run(boot)
      └─ asyncio.run(run_async(...))
           └─ FletSocketServer.start()      <- 这里才真正拉起桌面客户端 flet.exe
                └─ 客户端连上后才回调 boot   <- 首个界面在此渲染

关键结论：**模块导入全部发生在桌面客户端进程启动之前**。因此本模块顶层只做两件事：

1. 导入期立刻用守护线程开始预热重依赖（``preload.start()``），让
   「导入 sqlmodel / everytools / pystray…」与「拉起并初始化客户端」并行；
2. ``boot`` 里只做页面配置与最小接线，先渲染一个轻量占位帧，等预热结束后再挂载
   真正的根组件 ``csearch.view.app.App``。

相比之下，把重依赖与服务装配留在模块顶层会把约 1.6s 全部串行在客户端启动之前。
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import ui

from csearch import preload
from csearch.models.constants import (
    APP_TITLE,
    FONT_ASSET,
    FONT_FAMILY,
    ICON_ASSET,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
)

# assets 目录（包的上一级）
_ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"
)

# 模块导入即开始预热：此刻 ui.run 尚未调用，客户端也尚未被拉起，两者正好并行
preload.start()


# --------------------------------------------------------------------- 装配
def _build_services(page: ui.Page) -> Any:
    """构造 infra 实现 → 注入 service → 打包成 viewmodel 可见的 Services 容器。"""
    from csearch.infra import (
        AsyncioEventBus,
        DefaultBackgroundFactory,
        EverythingEngine,
        JsonBookmarkStore,
        JsonConfigStore,
        SqliteRunHistory,
        SystemFileOps,
        UiNotifier,
        UiTheme,
        UiWindowAdapter,
        Win32Screen,
    )
    from csearch.service import (
        BookmarkService,
        ConfigService,
        FileService,
        HistoryService,
        SearchService,
        SessionService,
    )
    from csearch.viewmodel.container import Services

    # 1) 基础设施（技术实现）
    screen = Win32Screen()
    bus = AsyncioEventBus()
    engine = EverythingEngine()
    config_store = JsonConfigStore()
    bookmark_store = JsonBookmarkStore()
    run_history = SqliteRunHistory()
    file_ops = SystemFileOps(screen)
    factory = DefaultBackgroundFactory(title=APP_TITLE)

    # 2) 服务（只依赖抽象端口）
    config = ConfigService(config_store)
    history = HistoryService(run_history)
    bookmarks = BookmarkService(bookmark_store)
    search = SearchService(engine, run_history)
    files = FileService(file_ops)
    session = SessionService(
        search=search, history=history, config=config, bus=bus, factory=factory
    )

    # 3) 视图模型可见的容器
    return Services(
        search=search,
        files=files,
        history=history,
        bookmarks=bookmarks,
        config=config,
        session=session,
        bus=bus,
        window=UiWindowAdapter(page),
        screen=screen,
        theme=UiTheme(page),
        notifier=UiNotifier(page),
    )


def _apply_theme(page: ui.Page, mode: str) -> None:
    """把 cs-ui 的主题运行时挂到页面上（一个种子色 → 整套 M3 色板）。

    走 ``ui.apply_theme`` 而不是手工拼 ``ui.Theme``：滚动条（桌面端 4px、悬停才显形）、
    弹出菜单、路由转场这些细节库里已经按桌面调好，自己写一份必然逐渐跑偏。

    ``mode`` 来自配置（system / light / dark）。``system`` 时由库监听
    ``page.platform_brightness`` 跟随系统，界面无需再关心。
    """
    state = ui.theme_state()
    state.primary = ui.PRIMARY_SEEDS["blue"]
    state.font_family = FONT_FAMILY
    state.set_mode(mode)
    ui.apply_theme(page, state)


def _configure_page(page: ui.Page, cfg: Any) -> None:
    """全局样式与字体（无边框紧凑桌面风）。"""
    page.title = APP_TITLE
    page.padding = 0
    page.spacing = 0
    page.fonts = {FONT_FAMILY: FONT_ASSET}
    page.bgcolor = ui.Colors.SURFACE_CONTAINER_LOWEST
    _apply_theme(page, cfg.theme)

    geometry = cfg.window
    page.window.title = APP_TITLE
    page.window.width, page.window.height = geometry.width, geometry.height
    page.window.min_width, page.window.min_height = (
        MIN_WINDOW_WIDTH,
        MIN_WINDOW_HEIGHT,
    )
    if geometry.left is not None and geometry.top is not None:
        page.window.left, page.window.top = geometry.left, geometry.top
    else:
        page.window.center()
    page.window.prevent_close = True  # 点 X 拦截为隐藏到托盘
    page.window.visible = not cfg.start_hidden
    try:
        page.window.icon = ICON_ASSET
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------- 首帧占位
@ui.component
def _Splash():
    """预热期间的首帧：极轻量，只为让窗口立刻有内容可画。"""
    return ui.Container(
        expand=True,
        bgcolor=ui.Colors.SURFACE_CONTAINER_LOWEST,
        alignment=ui.Alignment(0, 0),
        content=ui.Column(
            alignment=ui.MainAxisAlignment.CENTER,
            horizontal_alignment=ui.CrossAxisAlignment.CENTER,
            spacing=12,
            controls=[
                ui.ProgressRing(
                    width=22,
                    height=22,
                    stroke_width=2.4,
                    color=ui.Colors.PRIMARY,
                ),
                ui.Text(
                    "正在启动 CSearch…",
                    size=13,
                    color=ui.Colors.ON_SURFACE_VARIANT,
                ),
            ],
        ),
    )


@ui.component
def _Root():
    """根组件：预热未完成显示占位帧，完成后无缝切到真正的 App。"""
    ready, set_ready = ui.use_state(preload.done())

    if not ready:

        def _watch():
            async def _wait() -> None:
                # 在后台线程等待，避免阻塞事件循环（预热本身也是线程里跑的）
                await asyncio.to_thread(preload.wait)
                set_ready(True)  # 无论成功失败都放行，错误留给 App 自己呈现

            task = asyncio.create_task(_wait())
            return lambda: task.cancel()

        ui.use_effect(_watch, [])
        return _Splash()

    from csearch.view.app import App  # 已预热，此处近乎零成本

    return App()


# --------------------------------------------------------------------- 全局接线
def _on_keyboard(event: Any) -> None:
    """页面级快捷键：归一化为 KeyStroke 后交给键盘视图模型。"""
    from csearch.infra.ui_events import to_key_stroke
    from csearch.viewmodel.context import current

    context = current()
    if context is None:
        return
    asyncio.create_task(context.keyboard.handle(to_key_stroke(event)))


def _on_window_event(event: Any) -> None:
    """窗口事件：关闭→托盘 / 唤回焦点 / 缩放列适配 / 几何记忆。

    注意：flet 1.0 的窗口事件挂在 ``Window.on_event`` 上，Page 并没有
    ``on_window_event`` 字段。写成 ``page.on_window_event`` 只是个普通属性，flet
    永远不读——配合 ``prevent_close=True`` 会表现为「点 X 毫无反应且关不掉」。
    """
    from csearch.infra.ui_events import to_window_event
    from csearch.viewmodel.context import current

    context = current()
    if context is None:
        return
    window_event = to_window_event(event)
    if window_event is not None:
        context.window.handle(window_event)


async def boot(page: ui.Page) -> None:
    """Flet 入口：装配服务、配置页面、接线全局事件、渲染根组件。"""
    from csearch.viewmodel.container import install

    services = _build_services(page)
    install(services)

    _configure_page(page, services.config.load())

    page.on_keyboard_event = _on_keyboard
    page.window.on_event = _on_window_event

    page.render(_Root)  # 1.0 中 render 为同步挂载


def run() -> None:
    # Flet 1.0 默认 AppView.FLET_APP 即桌面原生窗口
    ui.run(boot, assets_dir=_ASSETS_DIR)
