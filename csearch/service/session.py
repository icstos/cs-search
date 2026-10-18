"""会话服务：启动装配（后台服务拉起 / 引擎探测 / 索引监听接线）与优雅退出。

只依赖抽象端口；Tray / Wheel 的构造通过 ``BackgroundFactory`` 工厂端口注入，
因此本层不知道 pystray / ctypes 钩子的存在。
"""

from __future__ import annotations

import asyncio

from csearch.models.entities import EngineStatus
from csearch.models.enums import BridgeEventType
from csearch.models.ports import BackgroundFactory, EventBus, Tray, Wheel
from csearch.service.config import ConfigService
from csearch.service.history import HistoryService
from csearch.service.search import SearchService


class SessionService:
    """长生命周期后台服务与引擎会话的编排（单窗口单例）。"""

    def __init__(
        self,
        *,
        search: SearchService,
        history: HistoryService,
        config: ConfigService,
        bus: EventBus,
        factory: BackgroundFactory,
    ) -> None:
        self._search = search
        self._history = history
        self._config = config
        self._bus = bus
        self._factory = factory
        self.tray: Tray | None = None
        self.wheel: Wheel | None = None

    # ------------------------------------------------------------------ 启动
    async def start_background(self) -> EngineStatus:
        """并发拉起三件互不依赖的启动工作，返回引擎状态。

        - 引擎状态探测（可能阻塞若干秒）；
        - 滚轮桥（安装低级钩子，需等安装结果，上限 3s）；
        - 托盘 + 全局热键 + 运行历史建表。
        全部走线程池，事件循环只负责等结果。
        """
        status, _, _ = await asyncio.gather(
            self._search.check_status(),
            asyncio.to_thread(self._start_wheel),
            asyncio.to_thread(self._start_tray_and_db),
        )
        return status

    def _start_wheel(self) -> None:
        """滚轮桥：部分环境不把 WM_MOUSEWHEEL 投递给 Flutter，用低级钩子兜底。"""
        wheel = self._factory.create_wheel(
            lambda delta: self._bus.emit(BridgeEventType.WHEEL.value, delta=delta)
        )
        self.wheel = wheel if wheel.start() else None

    def _start_tray_and_db(self) -> None:
        """托盘 + 全局热键 + 运行历史建表（彼此无依赖）。"""
        self._history.init_blocking()
        try:
            tray = self._factory.create_tray(
                hotkey=self._config.load().hotkey,
                # 热键固定激活窗口并置顶（不切换隐藏）；托盘左键单击才切换
                on_hotkey=lambda: self._bus.emit(BridgeEventType.SHOW.value),
                on_toggle=lambda: self._bus.emit(BridgeEventType.TOGGLE.value),
                on_show=lambda: self._bus.emit(BridgeEventType.SHOW.value),
                on_hide=lambda: self._bus.emit(BridgeEventType.HIDE.value),
                on_quit=lambda: self._bus.emit(BridgeEventType.QUIT.value),
            )
            # start() 返回 False = 托盘与热键均不可用：置空后 hide_to_tray 会降级为真退出
            self.tray = tray if tray.start() else None
        except Exception:  # noqa: BLE001
            self.tray = None

    # ------------------------------------------------------------------ 托盘 / 热键
    @property
    def tray_available(self) -> bool:
        """托盘或热键至少有一项可用（隐藏窗口后能否被唤回的唯一判据）。"""
        tray = self.tray
        return tray is not None and tray.running

    def set_hotkey(self, combo: str) -> bool:
        """动态更换全局热键；托盘未启动时不可用（返回 False 由调用方提示）。"""
        tray = self.tray
        return tray.set_hotkey(combo) if tray is not None else False

    def notify(self, message: str, title: str | None = None) -> None:
        if self.tray is not None:
            self.tray.notify(message, title)

    def set_wheel_swallow(self, value: bool) -> None:
        """结果列表激活时吞掉原生滚轮（由滚轮桥统一驱动）。"""
        if self.wheel is not None:
            self.wheel.swallow = value

    # ------------------------------------------------------------------ 退出
    def stop(self) -> None:
        """退出顺序：滚轮桥 → 托盘（内部先停热键）。

        索引变更同步由 viewmodel 层的 ``sync_loop`` 承担，随组件卸载被取消，
        本层无需收尾。
        """
        if self.wheel is not None:
            self.wheel.stop()
            self.wheel = None
        if self.tray is not None:
            self.tray.stop()
            self.tray = None
