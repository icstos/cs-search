"""界面设计令牌：颜色 / 间距 / 边框 / 对齐，全应用单一来源。

色值与重构前逐一对齐，保证视觉零变化；后续换肤只需改这里。
"""

from __future__ import annotations

import flet as ft


class C:
    """调色板（Google 中性灰 + 蓝主色，Everything 风格紧凑列表）。"""

    PAGE_BG = "#F7F8FA"
    SURFACE = "#FFFFFF"
    SURFACE_ALT = "#F6F8FA"   # 结果斑马行
    HEADER_BG = "#F1F3F4"     # 表头 / 未激活胶囊底
    SIDEBAR_BG = "#FAFBFC"
    BORDER = "#E4E7ED"        # 常规分隔线
    DIVIDER = "#DDE1E6"       # 列拖拽条（未悬停）
    BORDER_STRONG = "#DADCE0" # 胶囊未激活描边

    PRIMARY = "#1A73E8"
    PRIMARY_CONTAINER = "#E8F0FE"
    ON_PRIMARY = "#174EA6"    # 选中行主文本

    TEXT = "#202124"          # 主文本
    TEXT_STRONG = "#3C4043"
    TEXT_SUB = "#5F6368"      # 次要文本
    TEXT_HINT = "#9AA0A6"     # 占位 / 空态
    TEXT_FAINT = "#BDC1C6"    # 更弱提示

    DANGER = "#D93025"
    SUCCESS = "#188038"
    WARNING = "#F9AB00"


# 列对齐：-1 左 / 0 中 / 1 右
ALIGNMENT = {
    -1: ft.Alignment(-1, 0),
    0: ft.Alignment(0, 0),
    1: ft.Alignment(1, 0),
}
TEXT_ALIGN = {
    -1: ft.TextAlign.LEFT,
    0: ft.TextAlign.CENTER,
    1: ft.TextAlign.RIGHT,
}


def sym_padding(h: float, v: float) -> ft.Padding:
    """水平 h、垂直 v 的对称内边距。"""
    return ft.Padding(left=h, top=v, right=h, bottom=v)


def hairline(color: str = C.BORDER) -> ft.BorderSide:
    """1px 细边。"""
    return ft.BorderSide(1, color)


def top_border(color: str = C.BORDER) -> ft.Border:
    return ft.Border(top=hairline(color))


def bottom_border(color: str = C.BORDER) -> ft.Border:
    return ft.Border(bottom=hairline(color))


def radius_all(value: float) -> ft.BorderRadius:
    return ft.BorderRadius(value, value, value, value)
