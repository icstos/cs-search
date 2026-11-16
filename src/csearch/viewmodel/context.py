"""应用上下文：把「服务容器 + UI 状态 + 全部 ViewModel」组合成 view 层唯一入口。

view 组件只持有 ``AppContext``：渲染时读 ``ctx.state``，交互时调用 ``ctx.<vm>.<方法>``；
VM 之间需要协作时通过 ``ctx`` 互相访问，因此容器本身承担了实例装配与共享。

同时提供模块级「当前上下文」句柄，供页面级事件（键盘 / 窗口）在组件树之外回调。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from csearch.viewmodel.actions import ActionsViewModel
from csearch.viewmodel.bookmarks import BookmarksViewModel
from csearch.viewmodel.columns import ColumnsViewModel
from csearch.viewmodel.container import Services, current_services
from csearch.viewmodel.keyboard import KeyboardViewModel
from csearch.viewmodel.menu import MenuViewModel
from csearch.viewmodel.search import SearchViewModel
from csearch.viewmodel.selection import SelectionViewModel
from csearch.viewmodel.session import SessionViewModel
from csearch.viewmodel.settings import SettingsViewModel
from csearch.viewmodel.state import AppState
from csearch.viewmodel.window import WindowViewModel


@dataclass
class AppContext:
    """单窗口的 MVVM 上下文（services + state + viewmodels）。"""

    services: Services
    state: AppState

    search: SearchViewModel = field(init=False)
    selection: SelectionViewModel = field(init=False)
    actions: ActionsViewModel = field(init=False)
    bookmarks: BookmarksViewModel = field(init=False)
    columns: ColumnsViewModel = field(init=False)
    settings: SettingsViewModel = field(init=False)
    menu: MenuViewModel = field(init=False)
    window: WindowViewModel = field(init=False)
    keyboard: KeyboardViewModel = field(init=False)
    session: SessionViewModel = field(init=False)

    def __post_init__(self) -> None:
        # 顺序无关：各 VM 仅在方法调用期互相引用，构造期不访问兄弟实例
        self.search = SearchViewModel(self)
        self.selection = SelectionViewModel(self)
        self.actions = ActionsViewModel(self)
        self.bookmarks = BookmarksViewModel(self)
        self.columns = ColumnsViewModel(self)
        self.settings = SettingsViewModel(self)
        self.menu = MenuViewModel(self)
        self.window = WindowViewModel(self)
        self.keyboard = KeyboardViewModel(self)
        self.session = SessionViewModel(self)

    @classmethod
    def build(cls) -> AppContext:
        """按已安装的服务容器构建上下文（view 挂载时调用一次）。"""
        return cls(services=current_services(), state=AppState())


_current: AppContext | None = None


def set_current(context: AppContext) -> None:
    """记录当前窗口上下文（view 挂载时调用）。"""
    global _current
    _current = context


def current() -> AppContext | None:
    """当前窗口上下文；未挂载时为 None（早期到达的页面事件需容忍）。"""
    return _current
