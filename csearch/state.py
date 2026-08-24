"""全局状态管理：@ft.observable 数据类（UI = f(state)）+ 服务单例 + 线程安全事件桥。

设计：
- AppState 为唯一状态源，任何字段变更自动触发声明式组件重绘；
- Services 持有引擎/配置/书签/热键/托盘等长生命周期服务；
- EventBridge 用 queue.Queue 把热键/托盘/索引通知线程的事件安全地送进 asyncio 事件循环。
"""

from __future__ import annotations

import asyncio
import queue
from dataclasses import dataclass, field
from typing import Any, Optional

import flet as ft

from csearch.bookmarks import BookmarkStore
from csearch.config import ConfigStore
from csearch.search_engine import ResultItem, SearchEngine

PAGE_SIZE = 200       # 首次加载/增量加载的条数（性能关键：控制单次渲染规模）
MAX_LOADED = 5000     # 单次会话最多加载条数，避免超长列表拖垮 UI
DEBOUNCE_MS = 300     # 搜索框输入防抖


@dataclass
@ft.observable
class AppState:
    """应用唯一状态源。所有 UI 由该状态派生。"""

    # 搜索条件
    query: str = ""
    category: str = "all"
    time_range: str = "any"
    size_range: str = "any"

    # 排序
    sort_col: str = "name"
    sort_desc: bool = False

    # 结果
    results: list[ResultItem] = field(default_factory=list)
    total: int = 0
    total_files: int = 0
    total_folders: int = 0
    loaded: int = 0
    searching: bool = False
    elapsed_ms: float = 0.0

    # 引擎状态
    engine_ok: bool = True
    engine_msg: str = ""
    index_ready: bool = True
    engine_version: str = ""

    # 选中（索引集合；变更时整体替换以触发重绘）
    selected: set[int] = field(default_factory=set)
    select_anchor: int = -1          # shift 范围选择的锚点

    # 焦点导航（声明式 remount 实现 autofocus 切换）
    focus_target: str = "search"   # "search" | "list"
    focus_epoch: int = 0           # 变更强制重挂载（触发 autofocus）

    # 对话框
    dlg_delete: bool = False
    dlg_bookmark: bool = False
    dlg_hotkey: bool = False
    dlg_size: bool = False
    bookmark_edit_id: Optional[str] = None
    bm_name: str = ""
    hk_text: str = ""
    size_min: str = ""
    size_max: str = ""

    # 书签
    bookmarks: list[dict[str, Any]] = field(default_factory=list)

    # 内部（仅供 controller 使用）
    query_seq: int = 0                     # 竞态防护：新查询序号
    last_refresh_at: float = 0.0
    last_query_str: str = ""              # 最近一次执行的查询串（增量加载复用）
    last_sort_val: int = 0


class EventBridge:
    """跨线程事件桥：热键/托盘/索引通知线程 → asyncio 事件循环。"""

    def __init__(self) -> None:
        self._q: queue.Queue[dict[str, Any]] = queue.Queue()

    def put(self, ev: dict[str, Any]) -> None:
        try:
            self._q.put_nowait(ev)
        except Exception:  # noqa: BLE001
            pass

    async def get(self, timeout: float = 0.3) -> Optional[dict[str, Any]]:
        try:
            return await asyncio.to_thread(self._q.get, True, timeout)
        except Exception:  # noqa: BLE001
            return None


class Services:
    """长生命周期服务单例。"""

    def __init__(self) -> None:
        self.config = ConfigStore()
        self.bookmarks = BookmarkStore()
        self.engine = SearchEngine()
        self.bridge = EventBridge()
        self.search_lock = asyncio.Lock()   # 串行化搜索（SDK 单查询状态）
        self.tray: Any = None
        self.hotkey: Any = None
        self.quitting = False
        self.state: Any = None             # 由 App 组件挂载后注入（页面事件处理器使用）
        # controller 内部工作区
        self._debounce: Any = None
        self._refresh_task: Any = None
        self._geo_task: Any = None
        self._balloon_shown = False
        self._last_click_idx = -1
        self._last_click_t = 0.0


services = Services()
