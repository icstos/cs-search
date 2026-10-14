"""基础设施层：底层技术实现（Everything SDK / Win32 / SQLite / JSON / 托盘 / 滚轮桥）。

对外只暴露实现了 ``csearch.models.ports`` 的具体类，由组合根（bootstrap）注入到
service 层。本层不含任何业务逻辑，也不依赖 service / viewmodel / view。
"""

from csearch.infra.background_factory import DefaultBackgroundFactory
from csearch.infra.event_bus import AsyncioEventBus
from csearch.infra.everything_engine import EverythingEngine
from csearch.infra.file_ops import SystemFileOps
from csearch.infra.flet_events import to_key_stroke, to_window_event
from csearch.infra.flet_window import FletWindowAdapter
from csearch.infra.json_store import JsonBookmarkStore, JsonConfigStore
from csearch.infra.notifier import FletNotifier
from csearch.infra.run_history import SqliteRunHistory
from csearch.infra.tray import PystrayTray
from csearch.infra.wheel import LowLevelWheelBridge
from csearch.infra.win32 import Win32Screen

__all__ = [
    "AsyncioEventBus",
    "DefaultBackgroundFactory",
    "EverythingEngine",
    "FletNotifier",
    "FletWindowAdapter",
    "JsonBookmarkStore",
    "JsonConfigStore",
    "LowLevelWheelBridge",
    "PystrayTray",
    "SqliteRunHistory",
    "SystemFileOps",
    "Win32Screen",
    "to_key_stroke",
    "to_window_event",
]
