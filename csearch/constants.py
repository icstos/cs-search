"""全局常量、枚举与界面调参（UI 与查询构建共用，单一事实来源）。"""

from __future__ import annotations

from enum import StrEnum

# --------------------------------------------------------------------- 应用元信息
APP_TITLE = "CSearch - 极速文件搜索"
FONT_FAMILY = "AlibabaPuHuiTi"
FONT_ASSET = "fonts/AlibabaPuHuiTi-3-55-Regular.otf"
ICON_ASSET = "icon_windows.ico"

# --------------------------------------------------------------------- Everything 排序码
# Everything 1.5 服务器实测顺序式（升序 n / 降序 n+1）
SORT_NAME_ASC, SORT_NAME_DESC = 1, 2
SORT_PATH_ASC, SORT_PATH_DESC = 3, 4
SORT_SIZE_ASC, SORT_SIZE_DESC = 5, 6
SORT_DATE_MODIFIED_ASC, SORT_DATE_MODIFIED_DESC = 13, 14

# --------------------------------------------------------------------- 搜索调参
PAGE_SIZE = 200          # 每页加载条数
MAX_LOADED = 5000        # 单会话最大加载量
DEBOUNCE_MS = 150        # 输入防抖毫秒数
QUERY_TIMEOUT = 5.0      # content: 实时扫描看门狗（秒）
RESULT_CHUNK = 40        # 结果落地分片大小：批间让出事件循环，输入/滚轮优先
CHUNK_RENDER_GAP = 0.02  # 分片之间让出的秒数

# --------------------------------------------------------------------- 结果列表
ROW_HEIGHT = 30  # 固定行高（逻辑像素）：懒加载估算滚动范围 + 键盘跟随滚动
DEFAULT_COL_WIDTHS: dict[str, int] = {
    "name": 260, "path": 400, "size": 90, "mtime": 140, "run_count": 70,
}
MIN_COL_WIDTHS: dict[str, int] = {
    "name": 80, "path": 100, "size": 60, "mtime": 80, "run_count": 50,
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

# --------------------------------------------------------------------- 内部枚举
class Focus(StrEnum):
    """键盘焦点域：搜索框 / 结果列表。"""

    SEARCH = "search"
    LIST = "list"


class DialogKind(StrEnum):
    """模态对话框种类（None = 全部关闭）。"""

    BOOKMARK = "bookmark"
    HOTKEY = "hotkey"
    SIZE = "size"
    RUN_COUNT = "run_count"
