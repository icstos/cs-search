"""鼠标滚轮桥：系统级 WH_MOUSE_LL 钩子把滚轮事件转成滚动请求。

背景：flet 0.86 桌面客户端在某些环境（远程会话 / 虚拟桌面 / 特定显卡驱动等）
不把 WM_MOUSEWHEEL 投递给 Flutter 滚动控件，导致结果列表无法用滚轮滚动
（经实测：鼠标点击/键盘可用，滚轮与滚动条拖拽均无响应，但 scroll_to()
程序化滚动正常）。本模块用低级鼠标钩子兜底：滚轮发生在主窗口内时，
把滚动量经线程安全回调抛给调用方（由 logic 桥接回 asyncio 主循环，
对结果列表调用 scroll_to() 完成滚动）。

滚轮方向约定：Windows 中 WM_MOUSEWHEEL 的 delta 正负与“内容滚动方向”
相反（+120 = 向前滚 = 内容向上）。本模块统一转换为“正 = 内容向下滚动”
的像素增量后再上报，调用方直接按方向使用。

吞掉原生滚轮：flet 客户端收到 WM_MOUSEWHEEL 后也会自行滚动（不同环境
步长/方向不一，且与桥的跳转互相抵消，实测滚轮几乎无法滚动）。因此当
光标位于主窗口内且 swallow 开关开启（结果列表激活）时，钩子直接吞掉
该事件（不传给后续钩子与目标窗口），由桥统一驱动滚动，保证所有环境下
行为一致。书签面板等非结果列表场景 swallow 关闭，原生滚轮正常透传。

与托盘/热键遵循同一模式：钩子线程 → 线程安全队列 → asyncio 主循环。
不 import 任何 csearch 业务模块，完全解耦、失败降级（start() 返回 False）。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
from typing import Callable

WM_MOUSEWHEEL = 0x020A
WH_MOUSE_LL = 14
HC_ACTION = 0

# 滚轮每档（120）对应的滚动像素，接近 Flutter 桌面默认值
_PX_PER_NOTCH = 53.0

# 主窗口标题（查找句柄用，与 logic/tray 保持一致）
_WINDOW_TITLE = "CSearch - 极速文件搜索"

# 钩子回调原型
_LOWLEVELHOOKPROC = ctypes.WINFUNCTYPE(
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
    """滚轮桥：start() 启动钩子线程；窗口内滚轮量通过 on_wheel(delta_px) 回调上报。

    swallow：为 True 时（结果列表激活），吞掉主窗口内的原生滚轮事件，
    由桥统一滚动；为 False 时（书签面板等）原生滚轮正常透传。
    """

    def __init__(self, on_wheel: Callable[[int], None]) -> None:
        self._on_wheel = on_wheel
        self.swallow = False  # 由调用方（logic）按界面状态开关
        self._hwnd = 0  # 主窗口句柄缓存（避免每次全局滚轮都 FindWindow 枚举）
        self._hook: int | None = None
        self._thread: threading.Thread | None = None
        self._ready: threading.Event | None = None
        # 必须持有回调引用，防止被 GC 后钩子回调地址失效
        self._proc = _LOWLEVELHOOKPROC(self._callback)
        self._msg: wt.MSG = wt.MSG()

    # ------------------------------------------------------------ 对外接口
    def start(self) -> bool:
        """启动钩子线程（线程内安装钩子 + 消息泵，二者必须同线程）。
        失败返回 False（不影响主程序）。"""
        if self._hook is not None:
            return True
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="wheel", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3.0)
        return self._hook is not None

    def _run(self) -> None:
        """安装钩子并保持消息泵：低级钩子回调只会投递给安装线程的消息循环。"""
        try:
            user32 = ctypes.windll.user32
            user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _LOWLEVELHOOKPROC, wt.HINSTANCE, wt.DWORD]
            user32.SetWindowsHookExW.restype = wt.HHOOK
            user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
            user32.CallNextHookEx.restype = ctypes.c_ssize_t
            # 句柄类 API 显式声明为指针宽度：ctypes 默认按 32 位 int 返回，
            # 64 位下会截断 HWND，导致前台窗口/句柄相等比较出错
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
            # 装钩子时先解析一次主窗口句柄，后台滚轮即可零 FindWindow 直接放行
            self._hwnd = int(user32.FindWindowW(None, _WINDOW_TITLE) or 0)
            # 低级钩子的回调位于当前进程代码中：hMod 必须传 NULL（传 exe 句柄会失败）
            self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, None, 0)
        except Exception:  # noqa: BLE001
            self._hook = None
        self._ready.set()
        if not self._hook:
            return
        while self._hook is not None:
            r = user32.GetMessageW(ctypes.byref(self._msg), None, 0, 0)
            if r <= 0:
                break
            user32.TranslateMessage(ctypes.byref(self._msg))
            user32.DispatchMessageW(ctypes.byref(self._msg))

    def stop(self) -> None:
        """卸载钩子（幂等）。"""
        hook, self._hook = self._hook, None
        if hook:
            try:
                ctypes.windll.user32.UnhookWindowsHookEx(hook)
            except Exception:  # noqa: BLE001
                pass
        # 唤醒消息泵使其退出（PostThreadMessage 到钩子线程）
        if self._thread is not None and self._thread.is_alive():
            try:
                ctypes.windll.user32.PostThreadMessageW(self._thread.ident, 0x0012, 0, 0)  # WM_QUIT
            except Exception:  # noqa: BLE001
                pass
            self._thread.join(timeout=1.0)
        self._thread = None

    # ------------------------------------------------------------ 内部实现
    def _callback(self, n_code: int, wparam: int, lparam: int) -> int:
        if n_code == HC_ACTION and wparam == WM_MOUSEWHEEL:
            try:
                info = ctypes.cast(lparam, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
                # mouseData 高 16 位为有符号滚轮增量（±120 一档，触控板可为小数档）
                delta = ctypes.c_short(info.mouseData >> 16).value
                if delta and self._inside_window(info.pt):
                    # Windows 滚轮符号：+120=向前滚（内容向上），-120=向后滚
                    # （内容向下）；取反转换为“正=内容向下”的像素增量
                    px = -round(delta * _PX_PER_NOTCH / 120.0)
                    if px:
                        self._on_wheel(px)
                    # 结果列表激活时吞掉原生滚轮：flet 客户端自行滚动会与桥的
                    # 跳转互相抵消（实测每档净滚动几乎为零），统一由桥驱动
                    if self.swallow:
                        return 1
            except Exception:  # noqa: BLE001
                pass
        return ctypes.windll.user32.CallNextHookEx(self._hook, n_code, wparam, lparam)

    def _main_hwnd(self, user32) -> int:
        """主窗口句柄（缓存）：窗口被重建导致缓存句柄失效时，才按标题重新查找。"""
        hwnd = self._hwnd
        if hwnd and user32.IsWindow(hwnd):
            return hwnd
        self._hwnd = int(user32.FindWindowW(None, _WINDOW_TITLE) or 0)
        return self._hwnd

    @staticmethod
    def _foreground_is_ours(user32, hwnd: int) -> bool:
        """前台窗口是否属于本程序。

        GetForegroundWindow 可能返回本程序的下拉菜单/对话框等子窗口或被拥有
        窗口，而非主窗口本身，因此取其顶层根窗口（GetAncestor, GA_ROOT=2）再与
        主窗口比较；其他程序的根窗口必然不等于本程序句柄。"""
        fg = user32.GetForegroundWindow()
        if not fg:
            return False
        if fg == hwnd:
            return True
        root = user32.GetAncestor(fg, 2)  # GA_ROOT
        return bool(root) and root == hwnd

    def _inside_window(self, pt: wt.POINT) -> bool:
        """滚轮是否应交给本程序：主窗口可见、前台窗口属于本程序、光标落在其
        物理边界内，三者同时满足才成立；任一不满足都返回 False（调用方透传）。

        非前台绝不接管滚轮：WH_MOUSE_LL 是全局钩子，后台时若吞掉或拖慢滚轮
        回调，会表现为后台程序占用前台程序的滚轮；低级钩子回调一旦超过
        LowLevelHooksTimeout 还会被系统直接丢弃事件。因此把最便宜的“可见 +
        前台”判定放在最前，本程序在后台时只做轻量系统调用立即放行，绝不进行
        FindWindow 枚举（句柄已缓存）与 DWM 几何查询。

        命中测试坐标为物理像素，而本进程默认 DPI 感知下 GetWindowRect 返回
        虚拟化坐标，缩放显示器（125%/150%/175%…）上会误判；故用
        DwmGetWindowAttribute 取物理边界（DWMWA_EXTENDED_FRAME_BOUNDS=9，
        不受调用进程 DPI 感知影响），失败再回退 GetWindowRect。
        """
        try:
            user32 = ctypes.windll.user32
            hwnd = self._main_hwnd(user32)
            if not hwnd:
                return False
            if not user32.IsWindowVisible(hwnd):
                return False
            # 关键闸门：非前台立即透传，后续几何查询一律不做（零额外开销）
            if not self._foreground_is_ours(user32, hwnd):
                return False
            rect = wt.RECT()
            try:
                dwm = ctypes.windll.dwmapi
                if dwm.DwmGetWindowAttribute(
                    hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)
                ) != 0:  # DWMWA_EXTENDED_FRAME_BOUNDS=9，失败则回退 GetWindowRect
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
            except Exception:  # noqa: BLE001
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
            return rect.left <= pt.x <= rect.right and rect.top <= pt.y <= rect.bottom
        except Exception:  # noqa: BLE001
            return False
