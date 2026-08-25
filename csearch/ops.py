"""文件操作：全部系统原生调用，异常统一捕获返回友好信息。"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess

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


def open_items(items: list[ResultItem]) -> list[str]:
    """系统默认程序打开（多选批量）。返回错误列表。"""
    errors: list[str] = []
    for item in items:
        try:
            os.startfile(item.full_path)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{item.name}: {e}")
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


def delete_items(items: list[ResultItem], permanent: bool) -> list[str]:
    """删除（回收站 / 永久）。返回错误列表。"""
    errors: list[str] = []
    for item in items:
        try:
            if permanent:
                if item.is_folder:
                    shutil.rmtree(item.full_path)
                else:
                    os.remove(item.full_path)
            else:
                send2trash(item.full_path)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{item.name}: {e}")
    return errors


def open_folder(path: str) -> str | None:
    """用资源管理器打开文件夹。返回错误信息或 None。"""
    try:
        os.startfile(path)
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
