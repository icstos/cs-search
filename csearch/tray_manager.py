"""系统托盘（pystray）+ 全局热键（pynput）独立模块。

设计要点：
- 完全解耦：不 import 任何业务模块，通过构造参数注入的回调与主程序通信；
- 线程安全：托盘消息循环与热键监听均运行在守护子线程，互不阻塞主线程；
  所有 GUI 操作由调用方经事件桥抛回主线程执行（见 controller.session.bridge_loop），
  禁止在回调中直接操作 Flet 控件；
- 降级处理：图标加载失败用占位图、热键注册失败不影响托盘、托盘启动失败返回 False；
- 退出顺序：stop() 按「停止热键 → 销毁托盘」执行，幂等可重复调用。
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from typing import Any

# pystray / pynput / Pillow 为可选依赖：导入失败时模块仍可导入，start() 返回 False 降级
try:
    import pystray
    from pystray import Menu, MenuItem
except Exception:  # noqa: BLE001
    pystray = None  # type: ignore[assignment]
    Menu = MenuItem = None  # type: ignore[assignment,misc]

try:
    from PIL import Image, ImageDraw
except Exception:  # noqa: BLE001
    Image = ImageDraw = None  # type: ignore[assignment,misc]

try:
    from pynput import keyboard
except Exception:  # noqa: BLE001
    keyboard = None  # type: ignore[assignment]

# 托盘图标候选（兼容历史拼写 icon_widows.ico）
_ICON_CANDIDATES = ("icon_windows.ico", "icon_widows.ico", "icon.ico")
_CB = Callable[[], None]

# 热键组合 → pynput GlobalHotKeys 语法
_MOD_ALIASES = {"alt": "<alt>", "ctrl": "<ctrl>", "shift": "<shift>", "win": "<cmd>"}
_KEY_ALIASES = {"space": "<space>", "enter": "<enter>", "esc": "<esc>", "tab": "<tab>"}


def _default_icon_path() -> str | None:
    """定位项目 assets 目录下的托盘图标（相对本模块：csearch/../assets）。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assets = os.path.join(root, "assets")
    for name in _ICON_CANDIDATES:
        path = os.path.join(assets, name)
        if os.path.isfile(path):
            return path
    return None


def _make_placeholder_icon(size: int = 64):
    """生成占位图标（透明底 + 对角圆点），保证无图标文件时托盘仍可用。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r = size // 6
    draw.ellipse((size // 4 - r, size // 4 - r, size // 4 + r, size // 4 + r),
                 fill=(90, 130, 255, 255))
    draw.ellipse((size * 3 // 4 - r, size * 3 // 4 - r, size * 3 // 4 + r, size * 3 // 4 + r),
                 fill=(90, 130, 255, 255))
    return img


def _load_icon(icon_path: str | None):
    """加载托盘图标（PIL.Image）；失败返回占位图，绝不抛异常。"""
    if Image is None:
        return None
    if icon_path and os.path.isfile(icon_path):
        try:
            return Image.open(icon_path)
        except Exception:  # noqa: BLE001
            pass
    try:
        return _make_placeholder_icon()
    except Exception:  # noqa: BLE001
        return None


def _to_pynput(combo: str) -> str:
    """把 "alt+space" 风格组合串转换为 pynput GlobalHotKeys 语法。"""
    out: list[str] = []
    for part in (p.strip().lower() for p in combo.split("+") if p.strip()):
        if part in _MOD_ALIASES:
            token = _MOD_ALIASES[part]
        elif part in _KEY_ALIASES:
            token = _KEY_ALIASES[part]
        elif part.startswith("f") and part[1:].isdigit():
            token = f"<{part}>"
        else:
            token = part
        out.append(token)
    return "+".join(out)


class TrayManager:
    """系统托盘 + 全局热键管理器（守护子线程，线程安全）。

    回调（on_hotkey/on_toggle/on_show/on_hide/on_quit）运行在守护线程中，
    调用方必须把 GUI 操作经事件桥抛回主线程。
    """

    def __init__(
        self,
        *,
        icon_path: str | None = None,
        title: str = "CSearch",
        hotkey: str = "alt+space",
        on_hotkey: _CB | None = None,
        on_toggle: _CB | None = None,
        on_show: _CB | None = None,
        on_hide: _CB | None = None,
        on_quit: _CB | None = None,
        extra_menu_items: list | None = None,
    ) -> None:
        self._icon_path = icon_path if icon_path else _default_icon_path()
        self._title = title
        self._hotkey_combo = (hotkey or "").strip().lower()
        self._on_hotkey = on_hotkey
        self._on_toggle = on_toggle
        self._on_show = on_show
        self._on_hide = on_hide
        self._on_quit = on_quit
        self._extra_items = extra_menu_items or []

        self._lock = threading.Lock()
        self._started = False
        self._icon: Any = None
        self._thread: threading.Thread | None = None
        self._hotkey: Any = None

    # ------------------------------------------------------------ 生命周期
    def start(self) -> bool:
        """启动托盘与热键（守护线程）。返回托盘是否可用；热键失败不影响托盘。"""
        with self._lock:
            if self._started:
                return True
            if pystray is None:
                return False
            self._started = True

        # 1) 热键监听（失败仅记录，不阻断托盘）
        self._start_hotkey()

        # 2) 托盘（守护子线程运行 pystray 消息循环）
        try:
            icon = pystray.Icon(
                self._title,
                _load_icon(self._icon_path),
                self._title,
                self._build_menu(),
            )
            self._icon = icon
            self._thread = threading.Thread(target=icon.run, name="tray", daemon=True)
            self._thread.start()
            return True
        except Exception:  # noqa: BLE001 —— 托盘启动失败：清理并降级
            self.stop()
            return False

    def stop(self) -> None:
        """停止：先停热键，再销毁托盘（幂等）。"""
        with self._lock:
            if not self._started and self._hotkey is None and self._icon is None:
                return
            self._started = False
        self._stop_hotkey()
        icon, thread = self._icon, self._thread
        self._icon, self._thread = None, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:  # noqa: BLE001
                pass
        if thread is not None and thread.is_alive():
            thread.join(timeout=3)

    # ------------------------------------------------------------ 对外接口
    def set_hotkey(self, combo: str) -> bool:
        """动态更换全局热键；空串 = 禁用。返回是否注册成功。"""
        self._hotkey_combo = (combo or "").strip().lower()
        return self._start_hotkey()

    def toggle_window(self) -> None:
        """主动切换主窗口显示/隐藏（等价于左键单击托盘）。"""
        self._fire(self._on_toggle)

    def notify(self, message: str, title: str | None = None) -> None:
        """托盘气泡提示（尽力而为；平台不支持时静默忽略）。"""
        icon = self._icon
        if icon is None:
            return
        try:
            icon.notify(message, title or self._title)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ 内部实现
    def _build_menu(self):
        """构造右键菜单。

        - 隐藏的 default 项：左键单击触发第一个 default=True 的项（切换窗口）；
        - 显示/隐藏主窗口、分隔线、退出为常规项；extra 项追加在退出之前。
        """
        return Menu(
            MenuItem("", lambda icon, item: self._fire(self._on_toggle),
                     default=True, visible=False),
            MenuItem("显示主窗口", lambda icon, item: self._fire(self._on_show)),
            MenuItem("隐藏主窗口", lambda icon, item: self._fire(self._on_hide)),
            Menu.SEPARATOR,
            *(self._extra_items or []),
            MenuItem("退出程序", lambda icon, item: self._fire(self._on_quit)),
        )

    def _fire(self, cb: _CB | None) -> None:
        """在守护线程触发回调；异常吞掉，避免拖垮托盘/热键线程。"""
        if cb is None:
            return
        try:
            cb()
        except Exception:  # noqa: BLE001
            pass

    def _start_hotkey(self) -> bool:
        self._stop_hotkey()
        combo = self._hotkey_combo
        if not combo or keyboard is None:
            return not combo  # 空串 = 主动禁用，视为成功
        try:
            listener = keyboard.GlobalHotKeys(
                # 固定触发 on_hotkey（激活窗口）；未注入时回退 on_toggle
                {_to_pynput(combo): lambda: self._fire(self._on_hotkey or self._on_toggle)}
            )
            listener.daemon = True
            listener.start()
            self._hotkey = listener
            return True
        except Exception:  # noqa: BLE001 —— 注册失败（权限/被占用）：降级为无热键
            self._hotkey = None
            return False

    def _stop_hotkey(self) -> None:
        listener = self._hotkey
        self._hotkey = None
        if listener is not None:
            try:
                listener.stop()
            except Exception:  # noqa: BLE001
                pass
