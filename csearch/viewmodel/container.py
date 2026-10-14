"""服务容器：viewmodel 层可见的**全部能力入口**（只含抽象端口与 service 实例）。

由组合根（``csearch.bootstrap``）装配并 install；viewmodel 只通过本容器取用能力，
因此永远看不到 infra 的具体类型。
"""

from __future__ import annotations

from dataclasses import dataclass

from csearch.models.ports import EventBus, Notifier, Screen, ScrollTarget, Window
from csearch.service.bookmarks import BookmarkService
from csearch.service.config import ConfigService
from csearch.service.files import FileService
from csearch.service.history import HistoryService
from csearch.service.search import SearchService
from csearch.service.session import SessionService


@dataclass
class Services:
    """单窗口单例的能力容器。"""

    # ---- service 层实例 ----
    search: SearchService
    files: FileService
    history: HistoryService
    bookmarks: BookmarkService
    config: ConfigService
    session: SessionService

    # ---- 基础设施端口 ----
    bus: EventBus
    window: Window
    screen: Screen

    # ---- 由 view 层注册的运行时端口 ----
    notifier: Notifier | None = None       # 轻提示（SnackBar）
    scroll: ScrollTarget | None = None     # 结果列表滚动

    # ---- 跨组件一次性运行时标记 ----
    select_on_focus: bool = False  # 唤回窗口时全选搜索框内容
    wheel_acc: float = 0.0         # 滚轮绝对滚动累计值（on_scroll 持续同步）

    def toast(self, message: str) -> None:
        """轻提示（未注册 notifier 时静默忽略，不影响主流程）。"""
        if self.notifier is not None:
            self.notifier.notify(message)


_services: Services | None = None


def install(services: Services) -> None:
    """由组合根调用，安装全局服务容器（幂等覆盖）。"""
    global _services
    _services = services


def current_services() -> Services:
    """取当前服务容器；未装配时抛错（属于编程错误，不做静默降级）。"""
    if _services is None:
        raise RuntimeError("服务容器尚未装配：请先执行 csearch.bootstrap 的装配流程")
    return _services
