"""平台相关能力（当前为 Windows / user32 实现），对上层屏蔽 ctypes 细节。"""

from csearch.platform.win32 import (
    cursor_x,
    double_click_seconds,
    dpi_scale,
    ensure_window_on_screen,
    force_foreground_by_title,
    force_foreground_hwnd,
    modifier_state,
    mouse_down,
    raise_new_window,
    visible_top_windows,
)

__all__ = [
    "cursor_x",
    "double_click_seconds",
    "dpi_scale",
    "ensure_window_on_screen",
    "force_foreground_by_title",
    "force_foreground_hwnd",
    "modifier_state",
    "mouse_down",
    "raise_new_window",
    "visible_top_windows",
]
