"""后台服务工厂：让 service 层只依赖 ``BackgroundFactory`` 端口即可拿到托盘与滚轮桥。"""

from __future__ import annotations

from collections.abc import Callable

from csearch.infra.tray import PystrayTray
from csearch.infra.wheel import LowLevelWheelBridge
from csearch.models.ports import Tray, Wheel


class DefaultBackgroundFactory:
    """``BackgroundFactory`` 端口的默认实现（pystray 托盘 + 低级钩子滚轮桥）。"""

    def __init__(self, *, title: str, icon_path: str | None = None) -> None:
        self._title = title
        self._icon_path = icon_path

    def create_tray(
        self,
        *,
        hotkey: str,
        on_hotkey: Callable[[], None],
        on_toggle: Callable[[], None],
        on_show: Callable[[], None],
        on_hide: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> Tray:
        return PystrayTray(
            icon_path=self._icon_path,
            title=self._title,
            hotkey=hotkey,
            on_hotkey=on_hotkey,
            on_toggle=on_toggle,
            on_show=on_show,
            on_hide=on_hide,
            on_quit=on_quit,
        )

    def create_wheel(self, on_wheel: Callable[[int], None]) -> Wheel:
        return LowLevelWheelBridge(on_wheel)
