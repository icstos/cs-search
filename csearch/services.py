"""后台服务：跨线程事件桥 + 全局热键（pynput）+ 系统托盘（ctypes Shell_NotifyIconW）。"""

from __future__ import annotations

import asyncio
import ctypes
import ctypes.wintypes as wt
import os
import queue
import threading
from typing import Any

# ---------------- Windows 常量 ----------------
_WM_COMMAND = 0x0111
_WM_RBUTTONUP = 0x0205
_WM_LBUTTONDBLCLK = 0x0203
_WM_QUIT = 0x0012
_WM_DESTROY = 0x0002
_HWND_MESSAGE = ctypes.c_void_p(-3)
_NIM_ADD, _NIM_MODIFY, _NIM_DELETE = 0, 1, 2
_NIF_MESSAGE, _NIF_ICON, _NIF_TIP, _NIF_INFO = 1, 2, 4, 16
_NIIF_INFO = 1
_MF_STRING, _MF_SEPARATOR = 0, 0x800
_TPM_RIGHTBUTTON, _TPM_RETURNCMD, _TPM_NONOTIFY = 0x2, 0x100, 0x80
_IMAGE_ICON, _LR_LOADFROMFILE = 1, 0x10
_IDI_APPLICATION = 32512
_TRAY_MSG = 0x8001  # WM_APP+1 托盘回调
_NOTIFY_MSG = 0x8007  # WM_APP+7 Everything 索引变更通知
_CMD_SHOW, _CMD_QUIT = 1, 2

_WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_longlong, wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_longlong
)


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wt.UINT),
        ("lpfnWndProc", _WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
    ]


class _NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("hWnd", wt.HWND),
        ("uID", wt.UINT),
        ("uFlags", wt.UINT),
        ("uCallbackMessage", wt.UINT),
        ("hIcon", wt.HICON),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", wt.DWORD),
        ("dwStateMask", wt.DWORD),
        ("szInfo", ctypes.c_wchar * 256),
        ("uTimeoutOrVersion", wt.UINT),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", wt.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wt.HICON),
    ]


class EventBridge:
    """线程安全事件桥：热键/托盘/索引线程 → asyncio 事件循环。"""

    def __init__(self) -> None:
        self._q: queue.Queue[dict[str, str]] = queue.Queue()

    def emit(self, event: str) -> None:
        try:
            self._q.put_nowait({"type": event})
        except Exception:  # noqa: BLE001
            pass

    async def next(self, timeout: float = 0.3) -> dict[str, str] | None:
        try:
            return await asyncio.to_thread(self._q.get, True, timeout)
        except queue.Empty:
            return None


class HotkeyManager:
    """pynput 全局热键。"""

    def __init__(self, bridge: EventBridge) -> None:
        self._bridge = bridge
        self._listener: Any = None

    @staticmethod
    def _to_pynput(combo: str) -> str:
        mods = {"alt": "<alt>", "ctrl": "<ctrl>", "shift": "<shift>", "win": "<cmd>"}
        keys = {"space": "<space>", "enter": "<enter>", "esc": "<esc>", "tab": "<tab>"}
        out: list[str] = []
        for part in (p.strip().lower() for p in combo.split("+") if p.strip()):
            out.append(
                mods.get(
                    part,
                    keys.get(
                        part,
                        f"<{part}>"
                        if part.startswith("f") and part[1:].isdigit()
                        else part,
                    ),
                )
            )
        return "+".join(out)

    def set(self, combo: str) -> bool:
        """更换全局热键；空串 = 禁用。"""
        self.stop()
        combo = combo.strip().lower()
        if not combo:
            return True
        try:
            from pynput import keyboard

            self._listener = keyboard.GlobalHotKeys(
                {self._to_pynput(combo): lambda: self._bridge.emit("toggle")}
            )
            self._listener.daemon = True
            self._listener.start()
            return True
        except Exception:  # noqa: BLE001
            self._listener = None
            return False

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:  # noqa: BLE001
                pass
            self._listener = None


class TrayManager(threading.Thread):
    """系统托盘：隐藏消息窗口 + Shell_NotifyIconW + 右键菜单 + 索引变更通知窗口。"""

    def __init__(self, bridge: EventBridge, register_notify) -> None:
        super().__init__(name="tray", daemon=True)
        self._bridge = bridge
        self._register_notify = register_notify
        self._hwnd: int | None = None
        self._nid: _NOTIFYICONDATAW | None = None
        self._stop = False
        self._user32 = ctypes.windll.user32
        self._shell32 = ctypes.windll.shell32
        self._user32.DefWindowProcW.argtypes = [
            wt.HWND,
            wt.UINT,
            ctypes.c_size_t,
            ctypes.c_longlong,
        ]
        self._user32.DefWindowProcW.restype = ctypes.c_longlong

    # ------------------------------------------------------------ 生命周期
    def start_tray(self) -> None:
        self.start()

    def stop_tray(self) -> None:
        self._stop = True
        if self._hwnd:
            self._user32.PostMessageW(self._hwnd, _WM_QUIT, 0, 0)
        self.join(timeout=3)

    def balloon(self, title: str, text: str) -> None:
        if self._nid is None:
            return
        self._nid.szInfo = text[:255]
        self._nid.szInfoTitle = title[:63]
        self._nid.dwInfoFlags = _NIIF_INFO
        self._nid.uFlags |= _NIF_INFO
        self._shell32.Shell_NotifyIconW(_NIM_MODIFY, ctypes.byref(self._nid))
        self._nid.uFlags &= ~_NIF_INFO

    # ------------------------------------------------------------ 线程主体
    def run(self) -> None:
        try:
            self._hwnd = self._create_window()
            if not self._hwnd:
                return
            self._add_icon()
            if self._register_notify is not None:
                try:
                    self._register_notify(self._hwnd, _NOTIFY_MSG)
                except Exception:  # noqa: BLE001
                    pass
            msg = wt.MSG()
            while not self._stop:
                r = self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if r <= 0:
                    break
                self._user32.TranslateMessage(ctypes.byref(msg))
                self._user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            if self._nid is not None:
                self._shell32.Shell_NotifyIconW(_NIM_DELETE, ctypes.byref(self._nid))
            if self._hwnd:
                self._user32.DestroyWindow(self._hwnd)

    def _create_window(self) -> int | None:
        hinst = ctypes.windll.kernel32.GetModuleHandleW(None)
        wc = _WNDCLASSW()
        wc.lpfnWndProc = _WNDPROC(self._wnd_proc)
        wc.hInstance = hinst
        wc.lpszClassName = "CSearchTrayWindow"
        if not self._user32.RegisterClassW(ctypes.byref(wc)):
            return None
        hwnd = self._user32.CreateWindowExW(
            0,
            "CSearchTrayWindow",
            None,
            0,
            0,
            0,
            0,
            0,
            _HWND_MESSAGE,
            None,
            hinst,
            None,
        )
        return int(hwnd or 0) or None

    def _add_icon(self) -> None:
        if not self._hwnd:
            return
        ico = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets",
            "icon_windows.ico",
        )
        hicon = (
            self._user32.LoadImageW(None, ico, _IMAGE_ICON, 32, 32, _LR_LOADFROMFILE)
            if os.path.isfile(ico)
            else None
        )
        if not hicon:
            hicon = self._user32.LoadIconW(None, _IDI_APPLICATION)
        nid = _NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = _NIF_MESSAGE | _NIF_ICON | _NIF_TIP
        nid.uCallbackMessage = _TRAY_MSG
        nid.hIcon = hicon
        nid.szTip = "CSearch - 极速文件搜索"
        self._shell32.Shell_NotifyIconW(_NIM_ADD, ctypes.byref(nid))
        self._nid = nid

    def _wnd_proc(self, hwnd, uMsg, wParam, lParam):
        if uMsg == _TRAY_MSG:
            if lParam == _WM_RBUTTONUP:
                self._show_menu()
            elif lParam == _WM_LBUTTONDBLCLK:
                self._bridge.emit("toggle")
            return 0
        if uMsg == _WM_COMMAND:
            # 注意：模块常量名在 match 中会被当作捕获模式，这里用显式比较
            cmd = wParam & 0xFFFF
            if cmd == _CMD_SHOW:
                self._bridge.emit("show")
            elif cmd == _CMD_QUIT:
                self._bridge.emit("quit")
            return 0
        if uMsg == _NOTIFY_MSG:
            self._bridge.emit("index_changed")
            return 0
        if uMsg == _WM_DESTROY:
            self._user32.PostQuitMessage(0)
            return 0
        return self._user32.DefWindowProcW(hwnd, uMsg, wParam, lParam)

    def _show_menu(self) -> None:
        if not self._hwnd:
            return
        menu = self._user32.CreatePopupMenu()
        try:
            self._user32.AppendMenuW(menu, _MF_STRING, _CMD_SHOW, "显示主窗口")
            self._user32.AppendMenuW(menu, _MF_SEPARATOR, 0, None)
            self._user32.AppendMenuW(menu, _MF_STRING, _CMD_QUIT, "退出程序")
            pt = _POINT()
            self._user32.GetCursorPos(ctypes.byref(pt))
            self._user32.SetForegroundWindow(self._hwnd)
            cmd = self._user32.TrackPopupMenu(
                menu,
                _TPM_RIGHTBUTTON | _TPM_RETURNCMD | _TPM_NONOTIFY,
                pt.x,
                pt.y,
                0,
                self._hwnd,
                None,
            )
            if cmd:
                self._user32.PostMessageW(self._hwnd, _WM_COMMAND, cmd, 0)
        finally:
            self._user32.DestroyMenu(menu)
