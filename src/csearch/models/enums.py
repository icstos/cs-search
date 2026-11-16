"""状态枚举（纯值类型，无行为）。"""

from __future__ import annotations

from enum import StrEnum


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


class MenuKind(StrEnum):
    """右键菜单覆盖层的目标类型（None = 未打开）。

    使用根 Stack 自绘覆盖层，因此需要显式记录「菜单作用在谁身上」。
    """

    RESULT_ROW = "result_row"
    BOOKMARK = "bookmark"


class WindowEventKind(StrEnum):
    """窗口事件种类（把 Flet 的窗口事件归一化为与框架无关的枚举）。"""

    CLOSE = "close"
    SHOW = "show"
    RESTORE = "restore"
    RESIZED = "resized"
    MOVED = "moved"


class BridgeEventType(StrEnum):
    """后台线程 → 主线程事件桥的事件名。"""

    TOGGLE = "toggle"
    SHOW = "show"
    HIDE = "hide"
    QUIT = "quit"
    WHEEL = "wheel"
