"""抽象接口（端口）：层与层之间的唯一契约。

依赖倒置的落点：**高层（service / viewmodel / view）只依赖这里的 Protocol，
绝不 import 任何 infra 具体实现**；具体实现由组合根（bootstrap）注入。

约定：
- 只描述「能做什么」，不含实现与业务规则；
- 全部标记 ``@runtime_checkable``，便于在测试/装配阶段做结构校验。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol, runtime_checkable

from csearch.models.entities import (
    AppConfig,
    Bookmark,
    BridgeEvent,
    EngineStatus,
    ResultItem,
    SearchOutcome,
    WindowGeometry,
)


# ===================================================================== 基础设施端口
@runtime_checkable
class EventBus(Protocol):
    """跨线程事件桥：后台线程 emit，事件循环 next。"""

    def emit(self, event: str, **payload: object) -> None: ...

    async def next(self) -> BridgeEvent: ...


@runtime_checkable
class SearchEngine(Protocol):
    """Everything 查询内核（分页查询 / 排序 / 索引变更监听）。"""

    version: str

    @property
    def available(self) -> bool: ...

    @property
    def error_message(self) -> str: ...

    @property
    def notify_registered(self) -> bool: ...

    def check_status(self) -> EngineStatus: ...

    def build_query(
        self,
        keyword: str,
        category: str,
        time_range: str,
        size_range: str,
        regex: bool = False,
    ) -> str: ...

    def sort_value(self, column: str, desc: bool) -> int: ...

    def search(
        self, query: str, sort_val: int, offset: int = 0, count: int = 200
    ) -> SearchOutcome: ...

    def start_change_monitor(self, callback: Callable[[], None]) -> None: ...

    def stop_change_monitor(self) -> None: ...

    def try_register_notify_window(self, hwnd: int, msg_id: int) -> bool: ...


@runtime_checkable
class FileOps(Protocol):
    """文件系统操作（打开 / 定位 / 复制 / 回收站删除 / 启动 Everything）。"""

    def open_items(self, items: list[ResultItem]) -> list[str]: ...

    def reveal_items(self, items: list[ResultItem]) -> list[str]: ...

    def copy_paths(self, items: list[ResultItem]) -> str | None: ...

    def copy_names(self, items: list[ResultItem]) -> str | None: ...

    def delete_to_trash(self, items: list[ResultItem]) -> tuple[list[str], list[str]]: ...

    def open_folder(self, path: str) -> str | None: ...

    def open_url(self, url: str) -> None: ...

    def launch_everything(self) -> bool: ...


@runtime_checkable
class ConfigStore(Protocol):
    """应用配置持久化（JSON）。"""

    def load_config(self) -> AppConfig: ...

    def save_window(self, geometry: WindowGeometry) -> None: ...

    def save_hotkey(self, hotkey: str) -> None: ...


@runtime_checkable
class BookmarkStore(Protocol):
    """书签持久化（JSON）。"""

    def load_bookmarks(self) -> list[Bookmark]: ...

    def save_bookmarks(self, bookmarks: list[Bookmark]) -> None: ...


@runtime_checkable
class RunHistory(Protocol):
    """运行历史仓储（SQLite。同步 API，调用方负责入线程池）。"""

    def init_db(self) -> None: ...

    def get_counts(self, paths: Iterable[str]) -> dict[str, int]: ...

    def increment(self, paths: Iterable[str]) -> None: ...

    def set_count(self, path: str, count: int) -> None: ...


@runtime_checkable
class Tray(Protocol):
    """系统托盘 + 全局热键（守护子线程）。"""

    @property
    def running(self) -> bool: ...

    def start(self) -> bool: ...

    def stop(self) -> None: ...

    def set_hotkey(self, combo: str) -> bool: ...

    def toggle_window(self) -> None: ...

    def notify(self, message: str, title: str | None = None) -> None: ...


@runtime_checkable
class Wheel(Protocol):
    """滚轮桥（低级鼠标钩子兜底）。"""

    swallow: bool

    def start(self) -> bool: ...

    def stop(self) -> None: ...


@runtime_checkable
class Window(Protocol):
    """主窗口控制（对 Flet Page.window 的抽象，viewmodel 不直接触碰控件）。"""

    @property
    def title(self) -> str: ...

    def geometry(self) -> WindowGeometry: ...

    def logical_width(self) -> float: ...

    def viewport_size(self) -> tuple[float, float]: ...

    def is_visible(self) -> bool: ...

    def show(self) -> None: ...

    def hide(self) -> None: ...

    async def to_front(self) -> None: ...

    def set_prevent_close(self, value: bool) -> None: ...

    async def destroy(self) -> None: ...


@runtime_checkable
class Screen(Protocol):
    """Windows 底层能力（修饰键 / 光标 / 双击时间 / 多屏几何 / 窗口置前）。"""

    def modifier_state(self) -> tuple[bool, bool]: ...

    def cursor_x(self) -> int: ...

    def mouse_down(self) -> bool: ...

    def double_click_seconds(self) -> float: ...

    def dpi_scale(self, logical_width: float | None) -> float: ...

    def visible_top_windows(self) -> list[tuple[int, bool]]: ...

    def raise_new_window(self, before: list[tuple[int, bool]]) -> None: ...

    def ensure_window_on_screen(self) -> None: ...

    def force_foreground_by_title(self, title: str) -> None: ...


# ===================================================================== 视图端口
@runtime_checkable
class Notifier(Protocol):
    """轻提示出口（SnackBar）：由 view 层注册实现，viewmodel 只表达语义。"""

    def notify(self, message: str) -> None: ...


@runtime_checkable
class ScrollTarget(Protocol):
    """结果列表滚动目标：由 view 层注册，viewmodel 只调用抽象方法。"""

    async def scroll_to(self, offset: float) -> None: ...


# ===================================================================== 工厂端口
@runtime_checkable
class BackgroundFactory(Protocol):
    """后台服务工厂：由组合根实现，让 service 层无需知道 Tray/Wheel 的具体类型。"""

    def create_tray(
        self,
        *,
        hotkey: str,
        on_hotkey: Callable[[], None],
        on_toggle: Callable[[], None],
        on_show: Callable[[], None],
        on_hide: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> Tray: ...

    def create_wheel(self, on_wheel: Callable[[int], None]) -> Wheel: ...
