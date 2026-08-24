"""全局热键（pynput）+ 系统托盘（纯 ctypes Shell_NotifyIconW，零额外依赖）。

托盘线程同时创建一个隐藏消息窗口，兼任 Everything 索引变更通知窗口：
Everything_SetNotifyWindow(hwnd, WM_APP+7) → 收到索引更新消息 → 事件桥 → UI 静默刷新。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import threading
from typing import Any, Callable, Optional

# ---------------- Windows 常量 ----------------
WM_APP = 0x8000
WM_COMMAND = 0x0111
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203
WM_QUIT = 0x0012
WM_DESTROY = 0x0002
HWND_MESSAGE = ctypes.c_void_p(-3)
NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NIIF_INFO = 0x00000001
MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
TPM_RIGHTBUTTON = 0x00000002
TPM_RETURNCMD = 0x00000100
TPM_NONOTIFY = 0x00000080
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
IDI_APPLICATION = 32512
CW_USEDEFAULT = 0x80000000

_TRAY_CB_MSG = WM_APP + 1          # 托盘回调消息
_EVERYTHING_NOTIFY_MSG = WM_APP + 7  # Everything 索引变更通知消息
CMD_SHOW = 1
CMD_QUIT = 2

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_longlong)


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wt.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    """NOTIFYICONDATAW V3（含 GUID 与气球图标字段）。"""

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


class TrayManager(threading.Thread):
    """系统托盘：隐藏窗口 + Shell_NotifyIconW + 右键菜单。

    所有事件通过 out_queue 投递（线程安全），由 UI 侧事件桥消费。
    """

    def __init__(self, out_queue: Any, notify_register: Optional[Callable[[int, int], bool]] = None) -> None:
        super().__init__(name="tray", daemon=True)
        self._q = out_queue
        self._register_notify = notify_register  # engine.try_register_notify_window
        self._hwnd: Optional[int] = None
        self._hicon: Optional[int] = None
        self._nid: Optional[NOTIFYICONDATAW] = None
        self._running = threading.Event()
        self._stop_requested = False
        self._user32 = ctypes.windll.user32
        self._shell32 = ctypes.windll.shell32
        # 64 位下 LPARAM 为 64 位值：不声明签名会溢出（DefWindowProcW 默认按 32 位处理）
        self._user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_longlong]
        self._user32.DefWindowProcW.restype = ctypes.c_longlong

    # ------------------------------------------------------------ 公共接口
    def start_tray(self) -> None:
        self.start()

    def stop_tray(self) -> None:
        self._stop_requested = True
        if self._hwnd:
            self._user32.PostMessageW(self._hwnd, WM_QUIT, 0, 0)
        self.join(timeout=3)

    def show_balloon(self, title: str, text: str) -> None:
        """托盘气泡提示（线程安全）。"""
        if self._nid is None:
            return
        self._nid.szInfo = text[:255]
        self._nid.szInfoTitle = title[:63]
        self._nid.dwInfoFlags = NIIF_INFO
        self._nid.uFlags |= NIF_INFO
        self._shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))
        self._nid.uFlags &= ~NIF_INFO

    # ------------------------------------------------------------ 线程主体
    def run(self) -> None:
        try:
            self._hwnd = self._create_window()
            if not self._hwnd:
                return
            self._hicon = self._load_icon()
            self._add_icon()
            # 注册 Everything 索引变更通知（失败则由 UI 侧降级为轮询）
            if self._register_notify is not None:
                try:
                    self._register_notify(self._hwnd, _EVERYTHING_NOTIFY_MSG)
                except Exception:  # noqa: BLE001
                    pass
            self._running.set()
            self._message_loop()
        finally:
            self._cleanup()

    def _create_window(self) -> Optional[int]:
        hinst = ctypes.windll.kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = WNDPROC(self._wnd_proc)
        wc.hInstance = hinst
        wc.lpszClassName = "CSearchTrayWindow"
        if not self._user32.RegisterClassW(ctypes.byref(wc)):
            return None
        hwnd = self._user32.CreateWindowExW(
            0, "CSearchTrayWindow", None, 0,
            0, 0, 0, 0, HWND_MESSAGE, None, hinst, None,
        )
        return int(hwnd or 0) or None

    def _load_icon(self) -> Optional[int]:
        ico = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icon.ico")
        if os.path.isfile(ico):
            h = self._user32.LoadImageW(None, ico, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
            if h:
                return int(h)
        return int(self._user32.LoadIconW(None, IDI_APPLICATION))

    def _add_icon(self) -> None:
        if not self._hwnd or not self._hicon:
            return
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = _TRAY_CB_MSG
        nid.hIcon = self._hicon
        nid.szTip = "CSearch - 极速文件搜索"
        self._shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        self._nid = nid

    def _message_loop(self) -> None:
        msg = wt.MSG()
        while not self._stop_requested:
            ret = self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            self._user32.TranslateMessage(ctypes.byref(msg))
            self._user32.DispatchMessageW(ctypes.byref(msg))

    def _wnd_proc(self, hwnd, uMsg, wParam, lParam):
        if uMsg == _TRAY_CB_MSG:
            if lParam == WM_RBUTTONUP:
                self._show_menu()
                return 0
            if lParam == WM_LBUTTONDBLCLK:
                self._q.put({"type": "toggle"})
                return 0
        elif uMsg == WM_COMMAND:
            cmd = wParam & 0xFFFF
            if cmd == CMD_SHOW:
                self._q.put({"type": "show"})
            elif cmd == CMD_QUIT:
                self._q.put({"type": "quit"})
            return 0
        elif uMsg == _EVERYTHING_NOTIFY_MSG:
            # 索引变更 → 静默刷新（UI 侧去抖）
            self._q.put({"type": "index_changed"})
            return 0
        elif uMsg == WM_DESTROY:
            self._user32.PostQuitMessage(0)
            return 0
        return self._user32.DefWindowProcW(hwnd, uMsg, wParam, lParam)

    def _show_menu(self) -> None:
        menu = self._user32.CreatePopupMenu()
        try:
            self._user32.AppendMenuW(menu, MF_STRING, CMD_SHOW, "显示主窗口")
            self._user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            self._user32.AppendMenuW(menu, MF_STRING, CMD_QUIT, "退出程序")
            pt = POINT()
            self._user32.GetCursorPos(ctypes.byref(pt))
            self._user32.SetForegroundWindow(self._hwnd)
            cmd = self._user32.TrackPopupMenu(
                menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                pt.x, pt.y, 0, self._hwnd, None,
            )
            if cmd:
                self._user32.PostMessageW(self._hwnd, WM_COMMAND, cmd, 0)
        finally:
            self._user32.DestroyMenu(menu)

    def _cleanup(self) -> None:
        if self._nid is not None:
            self._shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
        if self._hwnd:
            self._user32.DestroyWindow(self._hwnd)


# ---------------------------------------------------------------- 全局热键
class HotkeyManager:
    """pynput 全局热键。监听线程内回调 → 事件桥（线程安全）。"""

    def __init__(self, out_queue: Any) -> None:
        self._q = out_queue
        self._listener: Any = None
        self._combo = ""

    @staticmethod
    def to_pynput(combo: str) -> str:
        """'alt+space' → '<alt>+<space>'（pynput GlobalHotKeys 格式）。"""
        mods = {"alt": "<alt>", "ctrl": "<ctrl>", "shift": "<shift>", "win": "<cmd>"}
        keys = {"space": "<space>", "enter": "<enter>", "esc": "<esc>", "tab": "<tab>"}
        parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
        out: list[str] = []
        for p in parts:
            if p in mods:
                out.append(mods[p])
            elif p in keys:
                out.append(keys[p])
            elif p.startswith("f") and p[1:].isdigit():
                out.append(f"<{p}>")
            elif len(p) == 1:
                out.append(p)
            else:
                out.append(p)
        return "+".join(out)

    def set_hotkey(self, combo: str) -> bool:
        """更换全局热键。返回是否成功注册。"""
        self.stop()
        self._combo = combo
        combo = combo.strip().lower()
        if not combo:
            return True  # 空 = 禁用热键
        try:
            from pynput import keyboard

            mapping = {self.to_pynput(combo): self._trigger}
            self._listener = keyboard.GlobalHotKeys(mapping)
            self._listener.daemon = True
            self._listener.start()
            return True
        except Exception:  # noqa: BLE001
            self._listener = None
            return False

    def _trigger(self) -> None:
        self._q.put({"type": "toggle"})

    @property
    def combo(self) -> str:
        return self._combo

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:  # noqa: BLE001
                pass
            self._listener = None
