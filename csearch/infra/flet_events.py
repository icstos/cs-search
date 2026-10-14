"""Flet 事件 → 领域事件 的归一化适配。

viewmodel 只认识 ``KeyStroke`` / ``WindowEventData``，不感知 flet 的事件对象；
所有框架细节（键名大小写与空间、事件类型枚举）在本模块收敛。
"""

from __future__ import annotations

from typing import Any

from csearch.models.entities import KeyStroke, WindowEventData
from csearch.models.enums import WindowEventKind

_KIND_BY_NAME: dict[str, WindowEventKind] = {
    "CLOSE": WindowEventKind.CLOSE,
    "SHOW": WindowEventKind.SHOW,
    "RESTORE": WindowEventKind.RESTORE,
    "RESIZED": WindowEventKind.RESIZED,
    "MOVED": WindowEventKind.MOVED,
}


def to_key_stroke(event: Any) -> KeyStroke:
    """Flet 键盘事件 → 归一化按键（键名形如 "Arrow Down"，此处去空格并小写）。"""
    key = str(getattr(event, "key", "") or "").lower().replace(" ", "")
    return KeyStroke(key=key, ctrl=bool(getattr(event, "ctrl", False)))


def to_window_event(event: Any) -> WindowEventData | None:
    """Flet 窗口事件 → 归一化窗口事件；无关类型返回 None。"""
    event_type = getattr(event, "type", None)
    name = getattr(event_type, "name", None)
    if not name:
        return None
    kind = _KIND_BY_NAME.get(str(name))
    return WindowEventData(kind) if kind is not None else None
