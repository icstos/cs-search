"""鼠标滚轮桥：系统级 WH_MOUSE_LL 钩子把滚轮事件转成滚动请求。

背景：Flet 桌面客户端在某些环境（远程会话 / 虚拟桌面 / 特定显卡驱动）不把
WM_MOUSEWHEEL 投递给 Flutter 滚动控件：鼠标点击/键盘可用，滚轮与滚动条拖拽
无响应，但 scroll_to() 程序化滚动正常。本模块用低级鼠标钩子兜底：滚轮发生在
主窗口内时，把滚动量经线程安全回调抛给调用方（再由 controller 桥接回 asyncio
主循环调用 scroll_to）。

方向约定：WM_MOUSEWHEEL 的 delta 与“内容滚动方向”相反（+120 = 向前滚 = 内容
向上）。本模块统一转换为“正 = 内容向下滚动”的像素增量后上报。

吞掉原生滚轮：客户端收到 WM_MOUSEWHEEL 后也会自行滚动，与桥的跳转互相抵消，
实测几乎无法滚动。因此光标位于主窗口且 swallow 开启（结果列表激活）时，钩子
直接吞掉事件，由桥统一驱动；书签面板等场景 swallow 关闭，原生滚轮正常透传。

非前台绝不接管：全局钩子在后台吞滚轮会表现为占用前台程序滚轮，且低级钩子回调
超过 LowLevelHooksTimeout 会被系统丢弃，故把最便宜的“可见 + 前台”判定前置。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
from collections.abc import Callable

from csearch.constants import APP_TITLE

WM_MOUSEWHEEL = 0x020A
WH_MOUSE_LL = 14
HC_ACTION = 0
# 滚轮每档（120）对应的滚动像素，接近 Flutter 桌面默认值
_PX_PER_NOTCH = 53.0
_DWMWA_EXTENDED_FRAME_BOUNDS = 9
_GA_ROOT = 2
_WM_QUIT = 0x0012

_LOWLEVEL_HOOK_PROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM
)


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wt.POINT),
        ("mouseData", wt.DWORD),
        ("flags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class WheelBridge:
    """滚轮桥：start() 启动钩子线程；窗口内滚轮量经 on_wheel(delta_px) 回调上报。

    swallow=True（结果列表激活）时吞掉主窗口内原生滚轮，由桥统一滚动；
    False（书签面板等）时原生滚轮透传。
    """

    def __init__(self, on_wheel: Callable[[int], None]) -> None:
        self._on_wheel = on_wheel
        self.swallow = False  # 由 controller 按界面状态开关
        self._hwnd = 0        # 主窗口句柄缓存（避免每次全局滚轮都 FindWindow）
        self._hook: int | None = None
        self._thread: threading.Thread | None = None
        self._ready: threading.Event | None = None
        # 必须持有回调引用，防止被 GC 后钩子回调地址失效
        self._proc = _LOWLEVEL_HOOK_PROC(self._callback)
        self._msg = wt.MSG()

    # ------------------------------------------------------------ 对外接口
    def start(self) -> bool:
        """启动钩子线程（安装钩子 + 消息泵必须同线程）。失败返回 False。"""
        if self._hook is not None:
            return True
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="wheel", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3.0)
        return self._hook is not None

    def stop(self) -> None:
        """卸载钩子并停止消息泵（幂等）。"""
        hook, self._hook = self._hook, None
        if hook:
            try:
                ctypes.windll.user32.UnhookWindowsHookEx(hook)
            except Exception:  # noqa: BLE001
                pass
        if self._thread is not None and self._thread.is_alive():
            try:  # PostThreadMessage 唤醒 GetMessage 使其退出
                ctypes.windll.user32.PostThreadMessageW(
                    self._thread.ident, _WM_QUIT, 0, 0
                )
            except Exception:  # noqa: BLE001
                pass
            self._thread.join(timeout=1.0)
        self._thread = None

    # ------------------------------------------------------------ 钩子线程
    def _run(self) -> None:
        """安装钩子并保持消息泵：低级钩子回调只投递给安装线程的消息循环。"""
        try:
            user32 = ctypes.windll.user32
            user32.SetWindowsHookExW.argtypes = [
                ctypes.c_int, _LOWLEVEL_HOOK_PROC, wt.HINSTANCE, wt.DWORD
            ]
            user32.SetWindowsHookExW.restype = wt.HHOOK
            user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
            user32.CallNextHookEx.restype = ctypes.c_ssize_t
            # 句柄类 API 显式声明指针宽度，避免 64 位下截断 HWND
            user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
            user32.FindWindowW.restype = wt.HWND
            user32.GetForegroundWindow.restype = wt.HWND
            user32.GetAncestor.argtypes = [wt.HWND, ctypes.c_uint]
            user32.GetAncestor.restype = wt.HWND
            user32.IsWindow.argtypes = [wt.HWND]
            user32.IsWindow.restype = wt.BOOL
            user32.IsWindowVisible.argtypes = [wt.HWND]
            user32.IsWindowVisible.restype = wt.BOOL
            user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
            user32.GetWindowRect.restype = wt.BOOL
            # 装钩子时解析一次主窗口句柄，后台滚轮零 FindWindow 放行
            self._hwnd = int(user32.FindWindowW(None, APP_TITLE) or 0)
            # 低级钩子回调位于本进程：hMod 必须传 NULL
            self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, None, 0)
        except Exception:  # noqa: BLE001
            self._hook = None
        self._ready.set()
        if not self._hook:
            return
        user32 = ctypes.windll.user32
        while self._hook is not None:
            result = user32.GetMessageW(ctypes.byref(self._msg), None, 0, 0)
            if result <= 0:
                break
            user32.TranslateMessage(ctypes.byref(self._msg))
            user32.DispatchMessageW(ctypes.byref(self._msg))

    # ------------------------------------------------------------ 回调
    def _callback(self, n_code: int, wparam: int, lparam: int) -> int:
        if n_code == HC_ACTION and wparam == WM_MOUSEWHEEL:
            try:
                info = ctypes.cast(lparam, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
                # mouseData 高 16 位为有符号滚轮增量（±120 一档，触控板可为小数档）
                delta = ctypes.c_short(info.mouseData >> 16).value
                if delta and self._inside_window(info.pt):
                    # 取反转换为“正 = 内容向下”的像素增量
                    px = -round(delta * _PX_PER_NOTCH / 120.0)
                    if px:
                        self._on_wheel(px)
                    if self.swallow:  # 结果列表激活：吞掉原生滚轮，由桥统一驱动
                        return 1
            except Exception:  # noqa: BLE001
                pass
        return ctypes.windll.user32.CallNextHookEx(self._hook, n_code, wparam, lparam)

    def _main_hwnd(self, user32) -> int:
        """主窗口句柄（缓存）：窗口重建导致缓存失效时才按标题重查。"""
        hwnd = self._hwnd
        if hwnd and user32.IsWindow(hwnd):
            return hwnd
        self._hwnd = int(user32.FindWindowW(None, APP_TITLE) or 0)
        return self._hwnd

    @staticmethod
    def _foreground_is_ours(user32, hwnd: int) -> bool:
        """前台窗口是否属于本程序（取顶层根窗口再比较，覆盖下拉/对话框等子窗口）。"""
        fg = user32.GetForegroundWindow()
        if not fg:
            return False
        if fg == hwnd:
            return True
        root = user32.GetAncestor(fg, _GA_ROOT)
        return bool(root) and root == hwnd

    def _inside_window(self, pt: wt.POINT) -> bool:
        """滚轮是否应交给本程序：主窗口可见 + 前台属于本程序 + 光标落在物理边界内。

        命中测试为物理像素，而 GetWindowRect 在不同 DPI 感知下返回虚拟化坐标，
        缩放显示器上会误判；故优先用 DwmGetWindowAttribute 取物理边界，失败回退。
        """
        try:
            user32 = ctypes.windll.user32
            hwnd = self._main_hwnd(user32)
            if not hwnd or not user32.IsWindowVisible(hwnd):
                return False
            # 关键闸门：非前台立即透传，后续几何查询一律不做（零额外开销）
            if not self._foreground_is_ours(user32, hwnd):
                return False
            rect = wt.RECT()
            try:
                dwm = ctypes.windll.dwmapi
                if dwm.DwmGetWindowAttribute(
                    hwnd, _DWMWA_EXTENDED_FRAME_BOUNDS,
                    ctypes.byref(rect), ctypes.sizeof(rect),
                ) != 0:
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
            except Exception:  # noqa: BLE001
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
            return rect.left <= pt.x <= rect.right and rect.top <= pt.y <= rect.bottom
        except Exception:  # noqa: BLE001
            return False
