"""核心数据结构（不可变优先的 dataclass，显示字段在读取时预计算）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from csearch.models.enums import WindowEventKind

# 事件桥的负载结构：{"type": 事件名, 其余为负载字段}
type BridgeEvent = dict[str, Any]


@dataclass
class ResultItem:
    """单条搜索结果（size_str/date_str 预计算，渲染零开销）。"""

    name: str
    path: str
    full_path: str
    size: int | None
    mtime: datetime | None
    is_folder: bool
    ext: str
    size_str: str
    date_str: str
    run_count: int = 0  # 本地运行历史次数（SQLite）


@dataclass(frozen=True)
class SearchOutcome:
    """一次分页查询的结果。"""

    rows: list[ResultItem]
    total: int
    # (total, 前 3 条 full_path+mtime+size)：索引变更签名对比
    signature: tuple[Any, ...]


@dataclass(frozen=True)
class EngineStatus:
    """Everything 服务探测结果。"""

    available: bool
    message: str = ""
    index_ready: bool = False


@dataclass
class Bookmark:
    """书签：搜索条件组合。"""

    id: str
    name: str
    query: str
    category: str
    time_range: str
    size_range: str


@dataclass
class WindowGeometry:
    """窗口几何（left/top 为 None 表示由系统决定）。"""

    width: int = 1040
    height: int = 680
    left: int | None = None
    top: int | None = None
    maximized: bool = False


@dataclass
class AppConfig:
    """应用配置（%APPDATA%/CSearch/config.json）。"""

    window: WindowGeometry
    hotkey: str
    start_hidden: bool = False


@dataclass(frozen=True)
class KeyStroke:
    """归一化后的按键输入（与 UI 框架无关）。"""

    key: str  # 小写、去空格的键名，如 "f5" / "arrowdown" / "enter"
    ctrl: bool = False


@dataclass(frozen=True)
class WindowEventData:
    """归一化后的窗口事件（与 UI 框架无关）。"""

    kind: WindowEventKind
