"""应用状态（Flet 原生可观测数据类，UI = f(state)）+ 服务单例。"""

from __future__ import annotations

from dataclasses import dataclass, field

import flet as ft

from csearch.engine import SearchEngine
from csearch.services import EventBridge
from csearch.tray_manager import TrayManager
from csearch.types import Bookmark, ResultItem


@dataclass
@ft.observable
class AppState:
    """唯一状态源：任何字段变更自动触发声明式组件重绘。"""

    # 搜索条件
    query: str = ""
    category: str = "all"
    time_range: str = "any"
    size_range: str = "any"
    sort_col: str = "name"
    sort_desc: bool = False

    # 结果
    results: list[ResultItem] = field(default_factory=list)
    total: int = 0
    searching: bool = False
    elapsed_ms: float = 0.0

    # 引擎状态
    engine_ok: bool = True
    engine_msg: str = ""
    index_ready: bool = True
    engine_version: str = ""

    # 选中（索引集合，变更时整体替换）
    selected: set[int] = field(default_factory=set)
    anchor: int = -1

    # 焦点导航（key 重挂载实现 autofocus 切换）
    focus: str = "search"      # "search" | "list"
    focus_epoch: int = 0

    # 结果列宽（表头与行共用，拖拽调整；单位逻辑像素）
    col_widths: dict[str, int] = field(default_factory=lambda: {
        "name": 260, "path": 400, "size": 90, "mtime": 140, "run_count": 70,
    })
    drag_col: str | None = None  # 正在拖拽调整的列
    hover_col: str | None = None  # 鼠标悬停的分隔条列
    row_width_snap: dict[str, int] | None = None  # 行控件重建的节流快照（拖拽时 60ms 更新一次）

    # 对话框（None = 关闭）
    dialog: str | None = None  # "delete" | "bookmark" | "hotkey" | "size" | "run_count"
    bm_edit_id: str | None = None
    bm_name: str = ""
    hotkey_text: str = ""
    size_min: str = ""
    size_max: str = ""
    run_count_text: str = "0"  # 设置运行次数对话框输入
    run_count_path: str = ""   # 设置运行次数的目标文件""

    # 书签
    bookmarks: list[Bookmark] = field(default_factory=list)

    # 内部
    seq: int = 0              # 竞态防护：新查询序号
    last_query: str = ""      # 最近执行的查询串（增量加载复用）
    last_sort: int = 0
    balloon_shown: bool = False
    quitting: bool = False


class Services:
    """长生命周期服务。"""

    def __init__(self) -> None:
        self.engine = SearchEngine()
        self.bridge = EventBridge()
        self.tray: TrayManager | None = None
        self.state: AppState | None = None
        self._debounce: object | None = None
        self._refresh: object | None = None
        self._geo: object | None = None
        self._last_click_i = -1
        self._last_click_t = 0.0
        self._drag_start = 0      # 列宽拖拽起始宽度
        self._drag_origin: float | None = None  # 拖拽起始指针全局 x


services = Services()
