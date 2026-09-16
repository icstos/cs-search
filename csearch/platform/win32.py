"""Windows user32/dwmapi 底层能力：键盘修饰键、光标、窗口置前与多屏几何。

统一约定：
- 全部为纯 ctypes 调用，不 import 任何业务模块；
- 任何异常都就地吞掉并返回安全默认值，绝不让平台调用拖垮主流程；
- 坐标/句柄类 API 显式声明指针宽度，避免 64 位下 HWND 被截断。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time
from collections.abc import Callable

from csearch.constants import APP_TITLE

# 虚拟键码
_VK_LBUTTON, _VK_MENU, _VK_CONTROL, _VK_SHIFT = 0x01, 0x12, 0x11, 0x10
# SetWindowPos flags
_SWP_NOSIZE, _SWP_NOZORDER, _SWP_NOACTIVATE = 0x0001, 0x0004, 0x0010
_SW_RESTORE = 9
_GA_ROOT = 2
# 窗口置前轮询兜底时长（秒）
_FOREGROUND_DEADLINE = 3.0
_FOREGROUND_INTERVAL = 0.05

_WND_ENUM_PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


def _user32():
    return ctypes.windll.user32


# --------------------------------------------------------------------- 键盘 / 鼠标
def modifier_state() -> tuple[bool, bool]:
    """读取 (Ctrl, Shift) 实时按下状态，用于点击时判断多选。"""
    try:
        user32 = _user32()
        return (
            bool(user32.GetAsyncKeyState(_VK_CONTROL) & 0x8000),
            bool(user32.GetAsyncKeyState(_VK_SHIFT) & 0x8000),
        )
    except Exception:  # noqa: BLE001
        return False, False


def cursor_x() -> int:
    """光标全局物理 X；失败返回 0。"""
    try:
        point = wt.POINT()
        _user32().GetCursorPos(ctypes.byref(point))
        return int(point.x)
    except Exception:  # noqa: BLE001
        return 0


def mouse_down() -> bool:
    """鼠标左键当前是否按下。"""
    try:
        return bool(_user32().GetAsyncKeyState(_VK_LBUTTON) & 0x8000)
    except Exception:  # noqa: BLE001
        return False


def double_click_seconds() -> float:
    """系统双击时间窗（秒），默认 500ms；失败回落到 0.5。

    自行判定双击时必须用它，写死 0.4s 会把「系统认可但稍慢」的双击漏判。
    """
    try:
        return max(0.2, _user32().GetDoubleClickTime() / 1000.0)
    except Exception:  # noqa: BLE001
        return 0.5


def dpi_scale(logical_width: float | None) -> float:
    """物理窗口宽 / 逻辑宽，用于把物理光标位移换算为逻辑像素。"""
    try:
        user32 = _user32()
        hwnd = user32.FindWindowW(None, APP_TITLE)
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        logical = float(logical_width or 1040)
        return (rect.right - rect.left) / logical if logical else 1.0
    except Exception:  # noqa: BLE001
        return 1.0


# --------------------------------------------------------------------- 窗口枚举 / 置前
def visible_top_windows() -> list[tuple[int, bool]]:
    """当前可见顶层窗口（EnumWindows 按 z-order 顶→底）：(hwnd, 是否最小化)。"""
    found: list[tuple[int, bool]] = []
    try:
        user32 = _user32()

        @_WND_ENUM_PROC
        def _enum(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd):
                found.append((int(hwnd), bool(user32.IsIconic(hwnd))))
            return True

        user32.EnumWindows(_enum, None)
    except Exception:  # noqa: BLE001
        return []
    return found


def force_foreground_hwnd(hwnd: int) -> None:
    """把指定窗口带到前台：先模拟 Alt 键打破 Windows 前台锁定，最小化则先还原。"""
    try:
        user32 = _user32()
        user32.keybd_event(_VK_MENU, 0, 0, 0)  # Alt down
        user32.keybd_event(_VK_MENU, 0, 2, 0)  # Alt up
        handle = ctypes.c_void_p(hwnd)
        if user32.IsIconic(handle):
            user32.ShowWindow(handle, _SW_RESTORE)
        user32.SetForegroundWindow(handle)
        user32.BringWindowToTop(handle)
    except Exception:  # noqa: BLE001
        pass


def raise_new_window(before: list[tuple[int, bool]]) -> None:
    """打开程序后轮询新出现/被还原的窗口并置前（兜底 3 秒）。

    覆盖全新进程启动（新窗口）与单实例复用（进程立即退出、窗口新建/还原）。
    """
    before_map = dict(before)
    deadline = time.monotonic() + _FOREGROUND_DEADLINE
    while time.monotonic() < deadline:
        for hwnd, iconic in visible_top_windows():
            was = before_map.get(hwnd)
            if was is None or (was and not iconic):
                force_foreground_hwnd(hwnd)
                return
        time.sleep(_FOREGROUND_INTERVAL)


def force_foreground_by_title(title: str) -> None:
    """按标题找窗口并抢前台焦点（托盘/热键唤回时绕过前台锁定）。"""
    try:
        user32 = _user32()
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            return
        user32.keybd_event(_VK_MENU, 0, 0, 0)
        user32.keybd_event(_VK_MENU, 0, 2, 0)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------- 多显示器几何
class _MonitorInfo(ctypes.Structure):
    """MONITORINFO（ctypes.wintypes 未内置）。"""

    _fields_ = [
        ("cbSize", wt.DWORD),
        ("rcMonitor", wt.RECT),
        ("rcWork", wt.RECT),
        ("dwFlags", wt.DWORD),
    ]


_MONITOR_ENUM_PROC = ctypes.WINFUNCTYPE(
    ctypes.c_bool,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(wt.RECT),
    ctypes.c_void_p,
)


def work_areas() -> list[tuple[int, int, int, int]]:
    """所有显示器工作区（物理像素）(left, top, right, bottom)；失败返回空。"""
    areas: list[tuple[int, int, int, int]] = []
    try:
        user32 = _user32()

        @_MONITOR_ENUM_PROC
        def _enum(_hmon, _hdc, lprect, _lparam):
            info = _MonitorInfo()
            info.cbSize = ctypes.sizeof(_MonitorInfo)
            if user32.GetMonitorInfoW(_hmon, ctypes.byref(info)):
                areas.append(
                    (info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom)
                )
            return True

        user32.EnumDisplayMonitors(None, None, _enum, None)
    except Exception:  # noqa: BLE001
        return []
    return areas


def ensure_window_on_screen() -> None:
    """窗口位置防跑出屏幕：与所有工作区交集不足 25% 时移回交集最大的显示器居中/贴边。

    多显示器布局变化会让保存的坐标失效（任务栏有程序、界面却看不到）。
    """
    try:
        user32 = _user32()
        hwnd = user32.FindWindowW(None, APP_TITLE)
        if not hwnd:
            return
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return
        areas = work_areas()
        if not areas:
            return

        best: tuple[int, int, int, int, int] | None = None  # (面积, l, t, r, b)
        for left, top, right, bottom in areas:
            inter_w = max(0, min(rect.right, right) - max(rect.left, left))
            inter_h = max(0, min(rect.bottom, bottom) - max(rect.top, top))
            area = inter_w * inter_h
            if best is None or area > best[0]:
                best = (area, left, top, right, bottom)
        if best is None or best[0] >= width * height * 0.25:
            return  # 主体可见，无需纠正

        _, wl, wtop, wr, wbottom = best
        # 窗口比工作区大时贴边，否则居中；保证标题栏落在屏内
        new_left = wl if width >= wr - wl else wl + (wr - wl - width) // 2
        new_top = (
            wtop if height >= wbottom - wtop else wtop + (wbottom - wtop - height) // 2
        )
        user32.SetWindowPos(
            hwnd, None, new_left, new_top, 0, 0,
            _SWP_NOSIZE | _SWP_NOZORDER | _SWP_NOACTIVATE,
        )
    except Exception:  # noqa: BLE001
        pass


# 便于按需传入自定义标题的场景（当前统一用 APP_TITLE，保留可调用别名）
ensure_on_screen: Callable[[], None] = ensure_window_on_screen
