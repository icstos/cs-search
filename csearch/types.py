"""核心类型与常量（Everything 1.5 专用）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# ---- 排序常量：Everything 1.5 服务器实测顺序式（升序 n / 降序 n+1） ----
SORT_NAME_ASC, SORT_NAME_DESC = 1, 2
SORT_PATH_ASC, SORT_PATH_DESC = 3, 4
SORT_SIZE_ASC, SORT_SIZE_DESC = 5, 6
SORT_DATE_MODIFIED_ASC, SORT_DATE_MODIFIED_DESC = 13, 14

# 每页加载条数 / 单会话最大加载量 / 输入防抖毫秒数
PAGE_SIZE = 200
MAX_LOADED = 5000
DEBOUNCE_MS = 100

# 查询看门狗（秒）：content: 未启用内容索引时触发实时扫描，超时保护
QUERY_TIMEOUT = 5.0

# 分类 / 时间 / 大小 过滤器选项（UI 与查询构建共用）
CATEGORIES: list[tuple[str, str]] = [
    ("all", "全部"),
    ("folder", "文件夹"),
    ("doc", "文档"),
    ("pic", "图片"),
    ("video", "视频"),
    ("audio", "音频"),
    ("archive", "压缩包"),
    ("exe", "可执行文件"),
]

TIME_RANGES: list[tuple[str, str]] = [
    ("any", "不限"),
    ("today", "今天"),
    ("week", "本周"),
    ("month", "本月"),
    ("year", "本年"),
]

SIZE_RANGES: list[tuple[str, str]] = [
    ("any", "不限"),
    ("lt1mb", "小于 1MB"),
    ("1mb-100mb", "1MB - 100MB"),
    ("100mb-1gb", "100MB - 1GB"),
    ("gt1gb", "大于 1GB"),
    ("custom", "自定义…"),
]


@dataclass
class ResultItem:
    """单条搜索结果（显示字段在读取时预计算，渲染零开销）。"""

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
    signature: tuple  # (total, 前3条 full_path+mtime+size)，用于索引变更对比


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
    width: int = 1040
    height: int = 680
    left: int | None = None
    top: int | None = None
    maximized: bool = False


@dataclass
class AppConfig:
    window: WindowGeometry = field(default_factory=WindowGeometry)
    hotkey: str = "alt+space"
    start_hidden: bool = False
