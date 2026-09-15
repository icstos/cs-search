"""核心数据模型（不可偏好的 dataclass，显示字段在读取时预计算）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


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


@dataclass
class SearchOutcome:
    """一次分页查询的结果。"""

    rows: list[ResultItem]
    total: int
    # (total, 前 3 条 full_path+mtime+size)：索引变更签名对比
    signature: tuple


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

    window: WindowGeometry = field(default_factory=WindowGeometry)
    hotkey: str = "alt+space"
    start_hidden: bool = False
