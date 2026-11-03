"""界面设计令牌：颜色 / 间距 / 边框 / 对齐，全应用单一来源。

色值与重构前逐一对齐，保证视觉零变化；后续换肤只需改这里。
"""

from __future__ import annotations

import ui


class C:
    """调色板（Google 中性灰 + 蓝主色，Everything 风格紧凑列表）。"""

    PAGE_BG = "#F7F8FA"
    SURFACE = "#FFFFFF"
    SURFACE_ALT = "#F6F8FA"   # 结果斑马行
    HEADER_BG = "#F1F3F4"     # 表头 / 未激活胶囊底
    SIDEBAR_BG = "#FAFBFC"
    BORDER = "#E4E7ED"        # 常规分隔线
    DIVIDER = "#DDE1E6"       # 列拖拽条（未悬停）
    BORDER_STRONG = "#DADCE0"  # 胶囊未激活描边

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
    -1: ui.Alignment(-1, 0),
    0: ui.Alignment(0, 0),
    1: ui.Alignment(1, 0),
}
TEXT_ALIGN = {
    -1: ui.TextAlign.LEFT,
    0: ui.TextAlign.CENTER,
    1: ui.TextAlign.RIGHT,
}


def sym_padding(h: float, v: float) -> ui.Padding:
    """水平 h、垂直 v 的对称内边距。"""
    return ui.Padding(left=h, top=v, right=h, bottom=v)


def hairline(color: str = C.BORDER) -> ui.BorderSide:
    """1px 细边。"""
    return ui.BorderSide(1, color)


def top_border(color: str = C.BORDER) -> ui.Border:
    return ui.Border(top=hairline(color))


def bottom_border(color: str = C.BORDER) -> ui.Border:
    return ui.Border(bottom=hairline(color))


def radius_all(value: float) -> ui.BorderRadius:
    return ui.BorderRadius(value, value, value, value)
