"""设计令牌：把 CSearch 的界面词汇落到 cs-ui 的 Material 3 设计系统上。

三条硬规则（改前先读，否则很容易写出「浅色好看、深色瞎眼」的代码）：

1. **结构色只引用 M3 角色**（``ui.Colors.*``），由 Flutter 在运行时按当前
   ``ColorScheme`` 解析。因此这里不维护两套明暗色值 —— 切主题是零成本的，
   也不可能出现硬编码灰在深色底上看不清的问题。
2. **``success`` / ``warning`` / ``danger`` 是 M3 没有的角色**，取值由 cs-ui 按
   当前生效模式算出来。所以它们是**函数**而不是常量：常量会在切主题后停在
   旧模式的色值上。
3. **尺寸不写裸数字**：间距 / 圆角 / 字号 / 图标 / 控件高 / 动效时长一律走 cs-ui
   的档位表。要整体调密度或风格，只改这一个文件。

本文件是视图层**唯一**的颜色与尺寸出口：视图里出现 ``"#1F6FEB"``、``18``、
``0.06`` 这类字面量就是走错了地方。
"""

from __future__ import annotations

import ui
from ui.core.tokens import (
    FONT_SIZE,
    FONT_WEIGHT,
    ICON_SIZE,
    RADIUS,
    SPACE,
    accent_soft,
    accent_text,
    elevation,
    focus_border,
    overlay,
    selected_layer,
    state_layer,
)

# --------------------------------------------------------------------- 尺寸档位
SP = SPACE  # 4px 基准网格：SP["2"] = 8
RAD = RADIUS  # xs 2 / sm 4 / md 6 / lg 8 / xl 12 / full 999
FS = FONT_SIZE  # caption 11 / small 12 / body 14 / title 16 / headline 20
FW = FONT_WEIGHT
ICON = ICON_SIZE  # 与「和谁同行」绑定：md 16 配正文 / lg 18 配标题 / 2xl 24 空态

# --------------------------------------------------------------------- 表面层级
# 从下到上：页面底 → 工具栏/状态栏 → 内容面 → 表头。深色模式下 Flutter 会把这些
# 角色解析成由深到浅的一组表面色，层级关系与浅色一致，无需分区维护。
PAGE = ui.Colors.SURFACE_CONTAINER_LOWEST
PANEL = ui.Colors.SURFACE_CONTAINER_LOW
SURFACE = ui.Colors.SURFACE
HEADER = ui.Colors.SURFACE_CONTAINER
BORDER = ui.Colors.OUTLINE_VARIANT

# --------------------------------------------------------------------- 文本层级
TEXT = ui.Colors.ON_SURFACE
TEXT_SUB = ui.Colors.ON_SURFACE_VARIANT
HINT = overlay(0.6)  # 占位 / 空态说明
FAINT = overlay(0.38)  # 更弱：无数据单元格（= M3 的禁用标签透明度）

# --------------------------------------------------------------------- 交互态
# 强调色走 cs-ui 的四联函数而不是裸 ``PRIMARY``：同一个"主色"在实底、实底上的
# 文字、压在表面上的文字、淡底这四种场合取值不同，函数是唯一入口。
ACCENT = accent_text("primary")  # 主色文字 / 图标 / 细边框
ACCENT_BG = accent_soft("primary")  # 12% 淡底（小面积：图标底座、选中胶囊）
SELECTED_BG = selected_layer("strong")  # 选中行：主色容器实底
ON_SELECTED = ui.Colors.ON_PRIMARY_CONTAINER
# 选中行里的次要文本：不能直接用 TEXT_SUB（那是灰的，压在蓝底上会脏）
SUB_ON_SELECTED = overlay(0.72, role=ui.Colors.ON_PRIMARY_CONTAINER)
HOVER = state_layer("hover")  # 悬停底色（菜单项 / 卡片），0.08 与 flet 内置控件同值
TRACK = state_layer("dragged")  # 列分隔条等中性线条：拖动档 0.16

# --------------------------------------------------------------------- 列对齐
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

# --------------------------------------------------------------------- 语义色
def success() -> str:
    """成功 / 有数据的强调色（按当前主题模式取值）。"""
    return accent_text("success")


def warning() -> str:
    """进行中 / 需留意的状态色。"""
    return accent_text("warning")


def danger() -> str:
    """错误 / 破坏性操作色。"""
    return accent_text("danger")


# --------------------------------------------------------------------- 形状与间距
def hairline(color: str = BORDER) -> ui.BorderSide:
    """1px 细边。"""
    return ui.BorderSide(1, color)


def top_border(color: str = BORDER) -> ui.Border:
    return ui.Border(top=hairline(color))


def bottom_border(color: str = BORDER) -> ui.Border:
    return ui.Border(bottom=hairline(color))


def sym_padding(h: float, v: float) -> ui.Padding:
    """水平 h、垂直 v 的对称内边距。"""
    return ui.Padding(left=h, top=v, right=h, bottom=v)


def radius_all(value: float) -> ui.BorderRadius:
    return ui.BorderRadius(value, value, value, value)


def floating_shadow(level: int = 2) -> ui.BoxShadow:
    """浮层阴影（右键菜单等浮在内容之上的面板）。"""
    return elevation(level)


def field_border(radius: float, *, focus_width: float = 1.5) -> dict:
    """描边式输入框的边框表：常态细灰线，聚焦时主色加粗。

    用 ``border={ControlState.X: OutlineInputBorder(...)}`` 这套三态写法，
    而不是已弃用的 ``focused_border_color`` / ``focused_border_width``。
    """
    return {
        ui.ControlState.DEFAULT: ui.OutlineInputBorder(
            side=hairline(), border_radius=radius_all(radius)
        ),
        ui.ControlState.FOCUSED: ui.OutlineInputBorder(
            side=focus_border(focus_width), border_radius=radius_all(radius)
        ),
        ui.ControlState.DISABLED: ui.OutlineInputBorder(
            side=hairline(), border_radius=radius_all(radius)
        ),
    }


def outline_field(**overrides: object) -> ui.TextField:
    """统一表单输入框外观：M3 描边式 + 主色聚焦环。

    对话框里的输入框都走这里，避免每个对话框各写一套 padding / 边框，
    也保证聚焦态在整个应用里是同一个视觉信号。
    """
    props: dict[str, object] = {
        "dense": True,
        "text_size": FS["body"],
        "border": field_border(RAD["md"]),
        "content_padding": ui.Padding.symmetric(horizontal=SP["3"], vertical=SP["2"]),
    }
    props.update(overrides)
    return ui.TextField(**props)  # type: ignore[arg-type]


__all__ = [
    "ACCENT",
    "ACCENT_BG",
    "ALIGNMENT",
    "BORDER",
    "FAINT",
    "FS",
    "FW",
    "HEADER",
    "HINT",
    "HOVER",
    "ICON",
    "ON_SELECTED",
    "PAGE",
    "PANEL",
    "RAD",
    "SELECTED_BG",
    "SP",
    "SUB_ON_SELECTED",
    "SURFACE",
    "TEXT",
    "TEXT_ALIGN",
    "TEXT_SUB",
    "TRACK",
    "bottom_border",
    "danger",
    "field_border",
    "floating_shadow",
    "hairline",
    "outline_field",
    "radius_all",
    "success",
    "sym_padding",
    "top_border",
    "warning",
]
