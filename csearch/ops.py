"""文件操作：全部系统原生调用，异常统一捕获并返回友好信息。"""

from __future__ import annotations

import os
import shutil
import subprocess

import pyperclip
from send2trash import send2trash

from csearch.models import ResultItem
from csearch.platform import raise_new_window, visible_top_windows


def open_items(items: list[ResultItem]) -> list[str]:
    """系统默认程序打开（多选批量）。返回错误列表。

    用 ShellExecute 启动的窗口可能因 Windows 前台锁定开在背后：启动前快照可见
    顶层窗口，启动后轮询新出现/被恢复的窗口并强制置前。
    """
    if not items:
        return []
    errors: list[str] = []
    before = visible_top_windows()
    for item in items:
        try:
            os.startfile(item.full_path)  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001
            errors.append(f"{item.name}: {e}")
    if len(errors) < len(items):
        raise_new_window(before)
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
    """删除选中项到回收站（无需确认，可恢复）。返回 (成功删除的路径, 错误信息)。"""
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
        before = visible_top_windows()
        os.startfile(path)  # type: ignore[attr-defined]
        raise_new_window(before)
        return None
    except Exception as e:  # noqa: BLE001
        return str(e)


def launch_everything() -> bool:
    """尝试启动 Everything；失败返回 False。"""
    program_files = os.environ.get("ProgramFiles", "")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(program_files, "Everything", "Everything.exe"),
        os.path.join(program_files_x86, "Everything", "Everything.exe"),
        os.path.join(local_appdata, "Programs", "Everything", "Everything.exe"),
        shutil.which("Everything"),
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            try:
                os.startfile(candidate)  # type: ignore[attr-defined]
                return True
            except Exception:  # noqa: BLE001
                return False
    return False
