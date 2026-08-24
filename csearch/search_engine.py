"""搜索内核：everything（everytools）SDK 封装 + 排序常量适配 + 分页查询 + 索引监听。

关键设计（性能与正确性）：
1. everytools 负责 DLL 装载/初始化与错误码映射（其 SortType 枚举与捆绑的 1.4.1 SDK 完全一致）。
   捆绑 DLL 为 Everything SDK 1.4.1（顺序式排序常量：名称1/2 路径3/4 大小5/6 修改时间13/14，
   与官方 Everything.h 1.4 完全一致）；若检测到 1.5+ SDK DLL（主版本号 >= 2），
   自动切换为 1.5 带符号排序常量（升序正/降序负）。
2. 分页查询（性能核心）：Everything_SetMax/Everything_SetOffset 限制单次 IPC 传输量。
   全量等待 QueryW(TRUE) 会传输全部命中行（20 万+ 结果需数秒）；
   而 offset/max 分页单次只传 200 行 —— 实测百万级索引查询仅 ~15ms，
   总数通过 Everything_GetTotResults 一次性获得，排序由 Everything 服务端完成。
3. SDK 为进程级单查询状态：engine._lock（threading）串行化所有查询，
   上层经 asyncio.to_thread 放入线程池执行，Flet 事件循环零阻塞。
4. 索引变更监听：优先 Everything_SetNotifyWindow（1.5+，托盘线程隐藏窗口收消息）；
   不可用时降级为 5s 轻量签名轮询（offset=0, max=3，毫秒级）。
"""

from __future__ import annotations

import ctypes
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

# ---- everytools（可能未安装：整体降级，UI 给出友好提示） ----
try:
    from everytools.core.dll_loader import get_dll_loader
    from everytools.exceptions import EverythingError  # noqa: F401
    _EVERYTOOLS_OK = True
except Exception:  # noqa: BLE001
    _EVERYTOOLS_OK = False

# ---- 排序常量：1.4.1 SDK 顺序式（官方 SDK 1.4 头文件 Everything.h 一致） ----
SORT_NAME_ASC, SORT_NAME_DESC = 1, 2
SORT_PATH_ASC, SORT_PATH_DESC = 3, 4
SORT_SIZE_ASC, SORT_SIZE_DESC = 5, 6
SORT_DATE_MODIFIED_ASC, SORT_DATE_MODIFIED_DESC = 13, 14
# ---- 1.5 SDK 带符号式（Everything 1.5 SDK：升序为正、降序为负） ----
_S15 = {
    "name": (1, -1), "path": (2, -2), "size": (3, -3), "mtime": (7, -7),
}

# 请求标志位（官方 SDK）
REQ_FILE_NAME = 0x00000001
REQ_PATH = 0x00000002
REQ_FULL_PATH = 0x00000004
REQ_EXTENSION = 0x00000008
REQ_SIZE = 0x00000010
REQ_DATE_MODIFIED = 0x00000040
REQ_ATTRIBUTES = 0x00000100
REQ_FLAGS = (REQ_FILE_NAME | REQ_PATH | REQ_FULL_PATH | REQ_EXTENSION
             | REQ_SIZE | REQ_DATE_MODIFIED | REQ_ATTRIBUTES)

# Everything 错误码（官方）
ERR_OK = 0
ERR_IPC = 2  # 与 Everything 通信失败（通常 = Everything 未运行）

_FILETIME_EPOCH = 116444736000000000
_PAGE_UNKNOWN = 0xFFFFFFFFFFFFFFFF

PAGE_SIZE = 200      # 首批/增量加载条数


@dataclass
class ResultItem:
    """单条搜索结果（显示字段在读取时预计算，渲染零开销）。"""

    name: str
    path: str
    full_path: str
    size: Optional[int]
    mtime: Optional[datetime]
    is_folder: bool
    ext: str
    attrs: int
    size_str: str = ""
    date_str: str = ""


@dataclass
class SearchOutcome:
    """一次分页查询的结果。"""

    rows: list[ResultItem]
    total: int
    total_files: int
    total_folders: int
    signature: tuple  # (total, 前3条 full_path+mtime+size) 用于索引变更对比


def _filetime_to_dt(value: int) -> Optional[datetime]:
    if not value or value == _PAGE_UNKNOWN:
        return None
    try:
        seconds = (value - _FILETIME_EPOCH) / 10_000_000.0
        return datetime.fromtimestamp(seconds)
    except Exception:  # noqa: BLE001
        return None


def human_size(size: Optional[int]) -> str:
    if size is None:
        return ""
    if size < 1024:
        return f"{size} B"
    for unit in ("KB", "MB", "GB", "TB"):
        size /= 1024.0
        if size < 1024:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} PB"


def fmt_dt(dt: Optional[datetime]) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


class EngineUnavailableError(RuntimeError):
    """Everything 服务不可用（未运行 / SDK 加载失败）。"""


class SearchTimeoutError(RuntimeError):
    """查询超时（服务端全量扫描等耗时操作），已安全中止。"""


class ContentSearchUnsupportedError(RuntimeError):
    """内容搜索需要 Everything 1.5+ 及内容索引。"""


# 查询超时保护：Everything 内容扫描等操作可能耗时极长，超时后中止并提示
QUERY_TIMEOUT = 5.0


class SearchEngine:
    """封装 everything（everytools）SDK：分页查询 / 排序 / 索引监听。"""

    def __init__(self) -> None:
        self._dll: Any = None
        self._lock = threading.Lock()      # SDK 进程级单查询串行化
        self._available = False
        self._err_msg = ""
        self.version = ""
        self._sdk15 = False                # 排序常量风格：1.5 带符号 / 1.4 顺序
        self._notify_registered = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_stop = threading.Event()
        self._monitor_cb: Optional[Callable[[], None]] = None
        self._last_query: tuple[Optional[str], int] = (None, 0)
        self._last_signature: tuple = ()
        self.init()

    # ------------------------------------------------------------------ 初始化
    def init(self) -> None:
        if not _EVERYTOOLS_OK:
            self._err_msg = "everytools 库未安装，请先执行 pip install everytools"
            return
        try:
            loader = get_dll_loader()
            self._dll = loader.everything_dll
            self.version = getattr(loader, "version", "")
            self._setup_signatures()
            try:
                self._sdk15 = int(self._dll.Everything_GetMajorVersion()) >= 2
            except Exception:  # noqa: BLE001
                self._sdk15 = False
            self._available = True
        except Exception as e:  # noqa: BLE001
            self._err_msg = f"Everything SDK DLL 加载失败: {e}"

    def _setup_signatures(self) -> None:
        """声明/覆盖 ctypes 函数签名（修正 everytools 声明错误的部分）。"""
        d = self._dll
        d.Everything_Reset.restype = None
        d.Everything_SetSearchW.argtypes = [ctypes.c_wchar_p]
        d.Everything_SetMatchCase.argtypes = [ctypes.c_bool]
        d.Everything_SetMatchPath.argtypes = [ctypes.c_bool]
        d.Everything_SetMatchWholeWord.argtypes = [ctypes.c_bool]
        d.Everything_SetRegex.argtypes = [ctypes.c_bool]
        d.Everything_SetSort.argtypes = [ctypes.c_int]
        d.Everything_SetRequestFlags.argtypes = [ctypes.c_uint]
        d.Everything_SetMax.argtypes = [ctypes.c_uint]
        d.Everything_SetOffset.argtypes = [ctypes.c_uint]
        d.Everything_QueryW.argtypes = [ctypes.c_bool]
        d.Everything_QueryW.restype = ctypes.c_bool
        d.Everything_GetNumResults.restype = ctypes.c_int
        d.Everything_GetTotResults.restype = ctypes.c_int
        d.Everything_GetTotFileResults.restype = ctypes.c_int
        d.Everything_GetTotFolderResults.restype = ctypes.c_int
        d.Everything_GetLastError.restype = ctypes.c_int
        d.Everything_IsDBLoaded.restype = ctypes.c_bool
        d.Everything_GetResultFileNameW.argtypes = [ctypes.c_int]
        d.Everything_GetResultFileNameW.restype = ctypes.c_wchar_p
        d.Everything_GetResultPathW.argtypes = [ctypes.c_int]
        d.Everything_GetResultPathW.restype = ctypes.c_wchar_p
        d.Everything_GetResultExtensionW.argtypes = [ctypes.c_int]
        d.Everything_GetResultExtensionW.restype = ctypes.c_wchar_p
        d.Everything_GetResultSize.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_ulonglong)]
        d.Everything_GetResultDateModified.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_ulonglong)]
        d.Everything_GetResultAttributes.argtypes = [ctypes.c_int]
        d.Everything_GetResultAttributes.restype = ctypes.c_uint
        d.Everything_IsFolderResult.argtypes = [ctypes.c_int]
        d.Everything_IsFolderResult.restype = ctypes.c_bool
        # 修正 everytools 的错误声明：正确签名为 (int, LPWSTR, int) -> int
        d.Everything_GetResultFullPathNameW.argtypes = [ctypes.c_int, ctypes.c_wchar_p, ctypes.c_int]
        d.Everything_GetResultFullPathNameW.restype = ctypes.c_int

    # ------------------------------------------------------------------ 状态
    @property
    def available(self) -> bool:
        return self._available

    @property
    def error_message(self) -> str:
        return self._err_msg

    @property
    def sdk_style(self) -> str:
        return "1.5" if self._sdk15 else "1.4"

    def check_status(self) -> tuple[bool, str, bool]:
        """检测 Everything 服务：返回 (可用, 提示信息, 索引是否已加载)。"""
        if not self._available:
            return False, self._err_msg, False
        try:
            with self._lock:
                self._dll.Everything_Reset()
                self._dll.Everything_SetSearchW("")
                self._dll.Everything_SetMax(1)  # 只需验证连通性，限制 IPC 传输量
                done = threading.Event()
                ok_box: list[bool] = [False]

                def _probe() -> None:
                    try:
                        ok_box[0] = bool(self._dll.Everything_QueryW(True))
                    finally:
                        done.set()

                worker = threading.Thread(target=_probe, name="sdk-probe", daemon=True)
                worker.start()
                if not done.wait(timeout=10):
                    try:
                        self._dll.Everything_Reset()
                    except Exception:  # noqa: BLE001
                        pass
                    return False, "Everything 响应超时（可能正在执行大量查询），请稍后重试", False
                ok = ok_box[0]
                if not ok:
                    err = int(self._dll.Everything_GetLastError())
                    if err == ERR_IPC:
                        return False, "未检测到 Everything 服务，请先启动 Everything", False
                    return False, f"Everything 查询失败（错误码 {err}）", False
                db = bool(self._dll.Everything_IsDBLoaded())
            return True, "", db
        except Exception as e:  # noqa: BLE001
            return False, f"Everything 检测异常: {e}", False

    # ------------------------------------------------------------------ 查询构建
    @staticmethod
    def build_query(keyword: str, category: str, time_range: str, size_range: str) -> str:
        """组合 Everything 原生查询串：分类/时间/大小过滤器与关键词叠加生效。

        分类用 Everything 1.5+ 原生搜索函数（folder:/doc:/pic:/video:/audio:/archive:/exe:），
        时间用 dm: 修改日期修饰符，大小用 size: 区间 —— 全部为 Everything 原生语法，
        与用户输入的关键词（含 ext:/content:/正则等）在服务端统一解析。
        """
        parts: list[str] = []
        cat = {
            "all": "", "folder": "folder:", "doc": "doc:", "pic": "pic:",
            "video": "video:", "audio": "audio:", "archive": "archive:", "exe": "exe:",
        }.get(category, "")
        if cat:
            parts.append(cat)
        time_q = {
            "any": "", "today": "dm:today", "week": "dm:thisweek",
            "month": "dm:thismonth", "year": "dm:thisyear",
        }.get(time_range, "")
        if time_q:
            parts.append(time_q)
        size_q = SearchEngine._size_query(size_range)
        if size_q:
            parts.append(size_q)
        kw = (keyword or "").strip()
        if kw:
            parts.append(kw)
        return " ".join(parts)

    @staticmethod
    def _size_query(size_range: str) -> str:
        if size_range == "any":
            return ""
        if size_range == "lt1mb":
            return "size:<1048576"
        if size_range == "1mb-100mb":
            return "size:1048576..104857600"
        if size_range == "100mb-1gb":
            return "size:104857600..1073741824"
        if size_range == "gt1gb":
            return "size:>1073741824"
        if size_range.startswith("custom:"):
            _, raw = size_range.split(":", 1)
            lo, _, hi = raw.partition(",")
            lo, hi = lo.strip(), hi.strip()
            if lo and hi:
                return f"size:{lo}..{hi}"
            if lo:
                return f"size:>{lo}"
            if hi:
                return f"size:<{hi}"
        return ""

    def sort_value(self, column: str, desc: bool) -> int:
        """列名 → SDK 排序常量（按 DLL 风格自动适配）。"""
        if self._sdk15:
            asc, dsc = _S15.get(column, (1, -1))
        else:
            table = {
                "name": (SORT_NAME_ASC, SORT_NAME_DESC),
                "path": (SORT_PATH_ASC, SORT_PATH_DESC),
                "size": (SORT_SIZE_ASC, SORT_SIZE_DESC),
                "mtime": (SORT_DATE_MODIFIED_ASC, SORT_DATE_MODIFIED_DESC),
            }
            asc, dsc = table.get(column, (SORT_NAME_ASC, SORT_NAME_DESC))
        return dsc if desc else asc

    # ------------------------------------------------------------------ 查询执行
    def search(self, query: str, sort_val: int, offset: int = 0, count: int = PAGE_SIZE) -> SearchOutcome:
        """分页查询（同步，线程池内调用，内部持锁）。

        核心性能点：SetMax/SetOffset 限制单次 IPC 传输量（默认 200 行），
        总数用 GetTotResults 获取，排序由 Everything 服务端完成。
        带看门狗超时保护：内容搜索等全量扫描场景超时后安全中止，UI 永不冻结。
        """
        if not self._available:
            raise EngineUnavailableError(self._err_msg)
        # 1.4 SDK 的 content: 会触发服务端全量文件扫描（可能数十分钟），前置拦截给出友好提示
        if "content:" in query.lower() and not self._sdk15:
            raise ContentSearchUnsupportedError(
                "内容搜索（content:）需要 Everything 1.5+ 并启用内容索引"
            )
        with self._lock:
            self._dll.Everything_Reset()
            self._dll.Everything_SetSearchW(query)
            self._dll.Everything_SetMatchCase(False)
            self._dll.Everything_SetMatchPath(False)
            self._dll.Everything_SetMatchWholeWord(False)
            self._dll.Everything_SetRegex(False)
            self._dll.Everything_SetSort(sort_val)
            self._dll.Everything_SetRequestFlags(REQ_FLAGS)
            self._dll.Everything_SetMax(count)
            self._dll.Everything_SetOffset(offset)
            # 看门狗：QueryW(TRUE) 阻塞等全部结果；超时则 Reset 中止并报错
            done = threading.Event()
            qerr: list[Exception] = []

            def _query() -> None:
                try:
                    qerr.append(bool(self._dll.Everything_QueryW(True)))
                except Exception as e:  # noqa: BLE001
                    qerr.append(e)
                finally:
                    done.set()

            worker = threading.Thread(target=_query, name="sdk-query", daemon=True)
            worker.start()
            if not done.wait(timeout=QUERY_TIMEOUT):
                try:
                    self._dll.Everything_Reset()  # 中止服务端扫描
                except Exception:  # noqa: BLE001
                    pass
                raise SearchTimeoutError(
                    f"搜索超时（>{QUERY_TIMEOUT:.0f}s）。内容搜索需在 Everything 中启用内容索引后才会快"
                )
            if not isinstance(qerr[0], bool):
                raise qerr[0]
            if not qerr[0]:
                err = int(self._dll.Everything_GetLastError())
                if err == ERR_IPC:
                    self._available = False
                    raise EngineUnavailableError("Everything 服务已断开，请重新启动 Everything")
                raise RuntimeError(f"Everything 查询失败（错误码 {err}）")
            total = int(self._dll.Everything_GetTotResults())
            files = int(self._dll.Everything_GetTotFileResults())
            folders = int(self._dll.Everything_GetTotFolderResults())
            rows: list[ResultItem] = []
            n = int(self._dll.Everything_GetNumResults())
            for i in range(n):
                try:
                    rows.append(self._read_item(i))
                except Exception:  # noqa: BLE001
                    continue  # 单条读取失败跳过，不中断整体
            sig_parts = [total]
            for i in range(min(3, n)):
                item = rows[i]
                sig_parts.append((item.full_path, item.mtime, item.size))
            sig = tuple(sig_parts)
            self._last_query = (query, sort_val)
            self._last_signature = sig
            return SearchOutcome(rows=rows, total=total, total_files=files,
                                 total_folders=folders, signature=sig)

    def _read_item(self, index: int) -> ResultItem:
        d = self._dll
        name = d.Everything_GetResultFileNameW(index) or ""
        path = d.Everything_GetResultPathW(index) or ""
        is_folder = bool(d.Everything_IsFolderResult(index))
        ext = (d.Everything_GetResultExtensionW(index) or "").lower()
        size_buf = ctypes.c_ulonglong(0)
        d.Everything_GetResultSize(index, ctypes.byref(size_buf))
        size = None if size_buf.value == _PAGE_UNKNOWN else int(size_buf.value)
        mtime_buf = ctypes.c_ulonglong(0)
        d.Everything_GetResultDateModified(index, ctypes.byref(mtime_buf))
        mtime = _filetime_to_dt(mtime_buf.value)
        attrs = int(d.Everything_GetResultAttributes(index))
        full_path = ""
        try:
            need = int(d.Everything_GetResultFullPathNameW(index, None, 0))
            if need > 0:
                buf = ctypes.create_unicode_buffer(need + 1)
                d.Everything_GetResultFullPathNameW(index, buf, need + 1)
                full_path = buf.value
        except Exception:  # noqa: BLE001
            full_path = ""
        if not full_path:
            full_path = os.path.join(path, name) if path else name
        return ResultItem(
            name=name, path=path, full_path=full_path, size=size, mtime=mtime,
            is_folder=is_folder, ext=ext, attrs=attrs,
            size_str=human_size(size), date_str=fmt_dt(mtime),
        )

    # ------------------------------------------------------------------ 索引变更监听
    def try_register_notify_window(self, hwnd: int, msg_id: int) -> bool:
        """注册 Everything 索引变更通知窗口（1.5+）。失败返回 False（调用方降级轮询）。"""
        if not self._available or not hwnd:
            return False
        try:
            fn = getattr(self._dll, "Everything_SetNotifyWindow", None)
            if fn is None:
                return False
            fn.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p]
            fn(hwnd, msg_id, 0)
            self._notify_registered = True
            return True
        except Exception:  # noqa: BLE001
            return False

    @property
    def notify_registered(self) -> bool:
        return self._notify_registered

    def start_change_monitor(self, callback: Callable[[], None]) -> None:
        """轮询降级方案：每 5s 重跑最近查询（offset=0, max=3，毫秒级）对比签名。"""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._monitor_stop.clear()
        self._monitor_cb = callback
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, name="index-monitor", daemon=True
        )
        self._monitor_thread.start()

    def _monitor_loop(self) -> None:
        while not self._monitor_stop.is_set():
            time.sleep(5)
            query, sort_val = self._last_query
            if query is None or self._monitor_stop.is_set():
                continue
            try:
                outcome = self.search(query, sort_val, offset=0, count=3)
                if outcome.signature != self._last_signature:
                    self._last_signature = outcome.signature
                    if self._monitor_cb:
                        try:
                            self._monitor_cb()
                        except Exception:  # noqa: BLE001
                            pass
            except Exception:  # noqa: BLE001
                continue

    def stop_change_monitor(self) -> None:
        self._monitor_stop.set()
        self._last_query = (None, 0)


# 便捷：分类/时间/大小选项元数据（UI 与查询构建共用）
CATEGORIES: list[tuple[str, str]] = [
    ("all", "全部"), ("folder", "文件夹"), ("doc", "文档"), ("pic", "图片"),
    ("video", "视频"), ("audio", "音频"), ("archive", "压缩包"), ("exe", "可执行文件"),
]

TIME_RANGES: list[tuple[str, str]] = [
    ("any", "不限"), ("today", "今天"), ("week", "本周"), ("month", "本月"), ("year", "本年"),
]

SIZE_RANGES: list[tuple[str, str]] = [
    ("any", "不限"), ("lt1mb", "小于 1MB"), ("1mb-100mb", "1MB - 100MB"),
    ("100mb-1gb", "100MB - 1GB"), ("gt1gb", "大于 1GB"), ("custom", "自定义…"),
]
