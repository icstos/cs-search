"""全局常量与界面调参（单一事实来源，五层均可依赖）。

只放「值」与由这些值派生的纯函数，不含任何 IO、状态或流程编排。
"""

from __future__ import annotations

# --------------------------------------------------------------------- 应用元信息
APP_TITLE = "CSearch - 极速文件搜索"
FONT_FAMILY = "AlibabaPuHuiTi"
FONT_ASSET = "fonts/AlibabaPuHuiTi-3-55-Regular.otf"
ICON_ASSET = "icon_windows.ico"

# --------------------------------------------------------------------- 全局热键
DEFAULT_HOTKEY = "alt+space"
#: 修饰键写法（含常见别名）；判定「热键是否为空转」的唯一依据
HOTKEY_MODIFIERS = frozenset(
    {"alt", "ctrl", "control", "shift", "win", "cmd", "super", "meta"}
)


def is_valid_hotkey(combo: str) -> bool:
    """热键规格是否合法：必须至少包含一个**非修饰键**，且不含空段。

    为什么这是硬性校验（改前先读）：pynput 的 ``HotKey`` 以「已按下键集合 == 组合
    集合」判定触发，所以纯修饰键组合（``alt`` / ``ctrl+alt``）就等于「单键热键」——
    仅按下 Alt 就会唤起窗口。而组合串解析会丢弃空段，于是 ``"alt+"`` 这种写错的
    组合也会静默退化成 ``<alt>``，同样一按 Alt 就激活。故在注册入口统一拒绝。
    """
    parts = [p.strip().lower() for p in (combo or "").split("+")]
    if any(not p for p in parts):
        return False  # "alt+" / "+space" / ""：残缺组合，会退化成单键热键
    return any(p not in HOTKEY_MODIFIERS for p in parts)


# --------------------------------------------------------------------- Everything 排序码
# Everything 1.5 服务器实测顺序式（升序 n / 降序 n+1）
SORT_NAME_ASC, SORT_NAME_DESC = 1, 2
SORT_PATH_ASC, SORT_PATH_DESC = 3, 4
SORT_SIZE_ASC, SORT_SIZE_DESC = 5, 6
SORT_DATE_MODIFIED_ASC, SORT_DATE_MODIFIED_DESC = 13, 14

# --------------------------------------------------------------------- 搜索调参
PAGE_SIZE = 200  # 每页加载条数
MAX_LOADED = 5000  # 单会话最大加载量
DEBOUNCE_MS = 150  # 输入防抖毫秒数
QUERY_TIMEOUT = 5.0  # content: 实时扫描看门狗（秒）
# 结果落地分片大小 / 批间让出秒数。
# 每新增一行控件，flet 都要为它及其子树做一次注册（_configure_dataclass），实测约
# 0.9ms/行；片数越多，「整体重走一遍列表」的次数就越多，总开销随之上升。实测 200 条
# 结果落地：40/0.02 五片 ≈ 308ms，100/0.01 两片 ≈ 202ms。取 100 兼顾「批间让出事件
# 循环」与总开销。
RESULT_CHUNK = 100  # 结果落地分片大小：批间让出事件循环，输入/滚轮优先
CHUNK_RENDER_GAP = 0.01  # 分片之间让出的秒数

# --------------------------------------------------------------------- 结果列表
ROW_HEIGHT = 30  # 固定行高（逻辑像素）：懒加载估算滚动范围 + 键盘跟随滚动
DEFAULT_COL_WIDTHS: dict[str, int] = {
    "name": 260,
    "path": 400,
    "size": 90,
    "mtime": 140,
    "run_count": 70,
}
MIN_COL_WIDTHS: dict[str, int] = {
    "name": 80,
    "path": 100,
    "size": 60,
    "mtime": 80,
    "run_count": 50,
}
MAX_COL_WIDTH = 900
# 列定义：(列键, 标题, 对齐 -1 左 / 0 中 / 1 右)
COLUMNS: list[tuple[str, str, int]] = [
    ("name", "名称", -1),
    ("path", "路径", -1),
    ("size", "大小", 1),
    ("mtime", "修改时间", 0),
    ("run_count", "次数", 1),
]

# --------------------------------------------------------------------- 过滤器选项
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

# --------------------------------------------------------------------- 自绘右键菜单几何
# 面板与命中夹紧共用：面板宽度、单条目高度、面板内边距、条目数（贴边夹紧用）。
MENU_WIDTH = 220
MENU_ITEM_HEIGHT = 30
MENU_PANEL_PADDING = 4  # 面板四周内边距（渲染）
MENU_CLAMP_PADDING = 8  # 贴边夹紧时的高度余量
MENU_ROW_ITEM_COUNT = 7  # 结果行菜单项数
MENU_BOOKMARK_ITEM_COUNT = 2  # 书签菜单项数

# --------------------------------------------------------------------- 窗口
MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT = 760, 480

# --------------------------------------------------------------------- 外部链接
EVERYTHING_DOWNLOAD_URL = "https://www.voidtools.com/zh-cn/downloads/"
