"""应用状态（Flet 原生可观测数据类，UI = f(state)）+ 长生命周期服务容器。"""

from __future__ import annotations

from dataclasses import dataclass, field

import flet as ft

from csearch.constants import DEFAULT_COL_WIDTHS, DialogKind, Focus, MenuKind
from csearch.engine import SearchEngine
from csearch.models import Bookmark, ResultItem
from csearch.services import EventBridge
from csearch.tray_manager import TrayManager
from csearch.wheel_bridge import WheelBridge


@dataclass
@ft.observable
class AppState:
    """唯一状态源：字段整体替换即自动触发声明式组件重绘。"""

    # ---- 搜索条件 ----
    query: str = ""
    # 程序化写入搜索框文本（清空 / 应用书签 / 启动回填）。搜索框控件由
    # SearchBar 用 use_memo 长期持有，只有它推进时才会重建并把文本下发客户端；
    # 用户输入路径走 on_change → state.query，期间绝不下发（见 ui/searchbar.py）。
    query_set: str = ""
    query_set_seq: int = 0
    category: str = "all"
    time_range: str = "any"
    size_range: str = "any"
    use_regex: bool = False  # 正则开关（内联 regex: 函数，参考 Everything）
    sort_col: str = "name"
    sort_desc: bool = False

    # ---- 结果 ----
    results: list[ResultItem] = field(default_factory=list)
    total: int = 0
    searching: bool = False
    elapsed_ms: float = 0.0
    max_ext: float = 0.0  # 列表当前最大滚动范围（on_scroll 同步，滚轮夹紧用）

    # ---- 引擎状态 ----
    engine_ok: bool = True
    engine_msg: str = ""
    index_ready: bool = True
    engine_version: str = ""

    # ---- 选中（集合变更时整体替换以触发重绘） ----
    selected: set[int] = field(default_factory=set)
    anchor: int = -1

    # ---- 焦点导航（key 重挂载实现 autofocus 切换） ----
    focus: Focus = Focus.SEARCH
    focus_epoch: int = 0

    # ---- 结果列宽（表头与行共用；单位逻辑像素） ----
    col_widths: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_COL_WIDTHS))
    drag_col: str | None = None       # 正在拖拽调整的列
    hover_col: str | None = None      # 鼠标悬停的分隔条列
    row_width_snap: dict[str, int] | None = None  # 行重建节流快照（拖拽时低频更新）

    # ---- 对话框（None = 关闭；删除无需确认，直接移入回收站） ----
    dialog: DialogKind | None = None
    bm_edit_id: str | None = None
    bm_name: str = ""
    hotkey_text: str = ""
    size_min: str = ""
    size_max: str = ""
    run_count_text: str = "0"
    run_count_path: str = ""

    # ---- 右键菜单覆盖层（页面逻辑坐标；MenuKind 为 None 表示未打开） ----
    menu_kind: MenuKind | None = None
    menu_x: float = 0.0
    menu_y: float = 0.0
    menu_row: int = -1          # 目标结果行
    menu_bookmark: str = ""     # 目标书签 id

    # ---- 书签 ----
    bookmarks: list[Bookmark] = field(default_factory=list)

    # ---- 搜索编排内部 ----
    seq: int = 0              # 竞态防护：最新查询序号
    last_query: str = ""      # 最近执行的查询串（增量加载复用）
    last_sort: int = 0
    loading_more: bool = False
    balloon_shown: bool = False
    quitting: bool = False


class Services:
    """长生命周期服务与跨组件运行时引用（单窗口单例）。

    - engine/bridge/tray/wheel：后台服务；
    - results_list：结果 ListView 的 Ref（程序化滚动用，由 Results 组件注册）；
    - state：根组件挂载后写回的当前状态（窗口/键盘事件可能早于挂载到达，故默认 None）；
    - 其余为跨层共享的一次性 UI 运行时标记。
    异步任务句柄由各自的 controller 模块管理，不放在此处。
    """

    def __init__(self) -> None:
        self.engine = SearchEngine()
        self.bridge = EventBridge()
        self.tray: TrayManager | None = None
        self.wheel: WheelBridge | None = None
        self.state: AppState | None = None  # 根组件挂载时写入（窗口/键盘事件可能更早到达）
        self.results_list = None  # ft.Ref[ft.ListView]，由 Results 组件注册
        self.select_on_focus = False  # 唤回窗口时全选搜索框内容（一次性标记）
        self.wheel_acc = 0.0          # 滚轮绝对滚动累计值（on_scroll 持续同步）


services = Services()
