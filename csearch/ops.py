"""文件操作：全部系统原生调用，异常统一捕获返回友好信息。"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import time

import pyperclip
from send2trash import send2trash

from csearch.types import ResultItem


def modifier_state() -> tuple[bool, bool]:
    """读取键盘修饰键实时状态（Ctrl, Shift），用于点击多选。"""
    try:
        user32 = ctypes.windll.user32
        return (
            bool(user32.GetAsyncKeyState(0x11) & 0x8000),
            bool(user32.GetAsyncKeyState(0x10) & 0x8000),
        )
    except Exception:  # noqa: BLE001
        return False, False


# ==================================================================== 打开置前
# 用 ShellExecute 启动的程序窗口可能因 Windows 前台锁定而开在背后：
# 启动前快照可见顶层窗口，启动后轮询新出现/被恢复的窗口并强制置前。
def _visible_top_windows() -> list[tuple[int, bool]]:
    """当前可见顶层窗口（EnumWindows 按 z-order 顶→底）：(hwnd, 是否最小化)。"""
    user32 = ctypes.windll.user32
    found: list[tuple[int, bool]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _enum(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            found.append((int(hwnd), bool(user32.IsIconic(hwnd))))
        return True

    user32.EnumWindows(_enum, None)
    return found


def _force_foreground(hwnd: int) -> None:
    """把指定窗口带到前台：先模拟 Alt 键打破 Windows 前台锁定。"""
    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(0x12, 0, 0, 0)  # VK_MENU down
        user32.keybd_event(0x12, 0, 2, 0)  # VK_MENU up
        h = ctypes.c_void_p(hwnd)
        if user32.IsIconic(h):
            user32.ShowWindow(h, 9)  # SW_RESTORE：最小化窗口先还原
        user32.SetForegroundWindow(h)
        user32.BringWindowToTop(h)
    except Exception:  # noqa: BLE001
        pass


def _raise_new_window(before: list[tuple[int, bool]]) -> None:
    """打开后轮询等待目标窗口出现/还原并置前（兜底 3 秒）。

    覆盖两种情况：全新进程启动（新窗口出现）；单实例应用复用已运行进程
    （ShellExecute 返回的进程立即退出，按 PID 找不到窗口，但窗口会新建或
    从最小化还原）。"""
    before_map = dict(before)
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        for hwnd, iconic in _visible_top_windows():
            was = before_map.get(hwnd)
            if was is None or (was and not iconic):
                _force_foreground(hwnd)
                return
        time.sleep(0.05)


def open_items(items: list[ResultItem]) -> list[str]:
    """系统默认程序打开（多选批量）。返回错误列表。"""
    errors: list[str] = []
    if not items:
        return errors
    before = _visible_top_windows()
    for item in items:
        try:
            os.startfile(item.full_path)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{item.name}: {e}")
    if len(errors) < len(items):
        _raise_new_window(before)  # 新打开的窗口置前
    return errors


def reveal_items(items: list[ResultItem]) -> list[str]:
    """资源管理器中打开并高亮选中。返回错误列表。"""
    errors: list[str] = []
    for item in items:
        try:
            subprocess.Popen(
                ["explorer.exe", "/select,", os.path.normpath(item.full_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:  # noqa: BLE001
            errors.append(f"{item.name}: {e}")
    return errors


def copy_paths(items: list[ResultItem]) -> str | None:
    """复制完整路径到剪贴板（多选换行拼接）。返回错误信息或 None。"""
    try:
        pyperclip.copy("\n".join(i.full_path for i in items))
        return None
    except Exception as e:  # noqa: BLE001
        return str(e)


def copy_names(items: list[ResultItem]) -> str | None:
    """仅复制文件名到剪贴板。返回错误信息或 None。"""
    try:
        pyperclip.copy("\n".join(i.name for i in items))
        return None
    except Exception as e:  # noqa: BLE001
        return str(e)


def delete_to_trash(items: list[ResultItem]) -> tuple[list[str], list[str]]:
    """删除选中项到回收站（无需确认，可恢复）。返回 (成功删除的 full_path 列表, 错误列表)。"""
    deleted: list[str] = []
    errors: list[str] = []
    for item in items:
        try:
            send2trash(item.full_path)
            deleted.append(item.full_path)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{item.name}: {e}")
    return deleted, errors


def open_folder(path: str) -> str | None:
    """用资源管理器打开文件夹。返回错误信息或 None。"""
    try:
        before = _visible_top_windows()
        os.startfile(path)
        _raise_new_window(before)  # 新开的资源管理器窗口置前
        return None
    except Exception as e:  # noqa: BLE001
        return str(e)


def launch_everything() -> bool:
    """尝试启动 Everything；失败返回 False。"""
    candidates = [
        os.path.join(os.environ.get("ProgramFiles", ""), "Everything", "Everything.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Everything", "Everything.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Everything", "Everything.exe"),
        shutil.which("Everything"),
    ]
    for cand in candidates:
        if cand and os.path.isfile(cand):
            try:
                os.startfile(cand)
                return True
            except Exception:  # noqa: BLE001
                return False
    return False
