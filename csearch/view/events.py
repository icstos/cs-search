"""Flet 事件读取工具：把控件事件中的坐标/状态提取为纯数据，交给 viewmodel。

view 层负责「读事件」（框架细节），viewmodel 负责「用数据」（业务语义），
两者通过本模块解耦。
"""

from __future__ import annotations

from typing import Any


def pointer_position(event: Any) -> tuple[float, float]:
    """从事件里取指针坐标（页面逻辑像素）。

    ``TapEvent.global_position`` 是页面内容逻辑坐标（bootstrap 已把 ``page.padding``
    设为 0，故与根 Stack 的 left/top 同处一个坐标系），直接可用。
    """
    global_position = getattr(event, "global_position", None)
    x = getattr(global_position, "x", None)
    if x is not None:
        return float(x), float(getattr(global_position, "y", 0.0) or 0.0)
    # 兜底：少数事件只带 global_x / global_y
    return float(getattr(event, "global_x", 0.0) or 0.0), float(
        getattr(event, "global_y", 0.0) or 0.0
    )


def pointer_dx(event: Any) -> float | None:
    """从拖拽事件里取指针全局 X（逻辑像素）；拿不到返回 None。"""
    global_position = getattr(event, "global_position", None)
    dx = getattr(global_position, "dx", None)
    return None if dx is None else float(dx)


def hover_entered(event: Any) -> bool:
    """on_hover 事件的 data 为字符串 "true" / "false"。"""
    return str(getattr(event, "data", "")) == "true"
