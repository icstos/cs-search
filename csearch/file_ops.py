"""文件操作封装：全部走系统原生 API，异常统一捕获并返回友好信息。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Iterable, Optional

import ctypes
import pyperclip
from send2trash import send2trash

from csearch.search_engine import ResultItem

# explorer /select 的参数分隔写法：列表形式避免引号转义问题
_EXPLORER = "explorer.exe"


def modifier_state() -> tuple[bool, bool]:
    """读取键盘修饰键实时状态（Ctrl, Shift），用于点击多选（GetAsyncKeyState）。"""
    try:
        user32 = ctypes.windll.user32
        ctrl = bool(user32.GetAsyncKeyState(0x11) & 0x8000)
        shift = bool(user32.GetAsyncKeyState(0x10) & 0x8000)
        return ctrl, shift
    except Exception:  # noqa: BLE001
        return False, False


def open_items(items: Iterable[ResultItem]) -> tuple[int, list[str]]:
    """用系统默认程序打开文件/文件夹（多选批量）。返回 (成功数, 错误列表)。"""
    ok, errors = 0, []
    for item in items:
        try:
            os.startfile(item.full_path)  # noqa: S606 - Windows 原生打开
            ok += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"{item.name}: {e}")
    return ok, errors


def reveal_items(items: Iterable[ResultItem]) -> tuple[int, list[str]]:
    """在资源管理器中打开并高亮选中（多选时逐条定位）。"""
    ok, errors = 0, []
    for item in items:
        try:
            subprocess.Popen(
                [_EXPLORER, "/select,", os.path.normpath(item.full_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            ok += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"{item.name}: {e}")
    return ok, errors


def copy_paths(items: Iterable[ResultItem]) -> tuple[int, Optional[str]]:
    """复制完整路径到剪贴板（多选换行拼接）。"""
    try:
        pyperclip.copy("\n".join(i.full_path for i in items))
        return len(list(items)), None
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def copy_names(items: Iterable[ResultItem]) -> tuple[int, Optional[str]]:
    """仅复制文件名到剪贴板。"""
    try:
        pyperclip.copy("\n".join(i.name for i in items))
        return len(list(items)), None
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def delete_items(items: Iterable[ResultItem], permanent: bool = False) -> tuple[int, list[str]]:
    """删除文件/文件夹。

    permanent=False -> 回收站（send2trash）
    permanent=True  -> 永久删除（文件 os.remove / 文件夹 shutil.rmtree）
    """
    ok, errors = 0, []
    for item in items:
        try:
            if permanent:
                if item.is_folder:
                    shutil.rmtree(item.full_path)
                else:
                    os.remove(item.full_path)
            else:
                send2trash(item.full_path)
            ok += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"{item.name}: {e}")
    return ok, errors


def launch_everything() -> bool:
    """尝试启动 Everything；找不到则返回 False（调用方提示下载）。"""
    candidates = [
        os.path.join(os.environ.get("ProgramFiles", ""), "Everything", "Everything.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Everything", "Everything.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Everything", "Everything.exe"),
        shutil.which("Everything"),
    ]
    for cand in candidates:
        if cand and os.path.isfile(cand):
            try:
                os.startfile(cand)  # noqa: S606
                return True
            except Exception:  # noqa: BLE001
                return False
    return False


def open_url(url: str) -> None:
    """打开网页（Everything 下载页等）。"""
    try:
        import webbrowser

        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass
