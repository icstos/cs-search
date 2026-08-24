"""搜索内核：everything（everytools）SDK 封装，Everything 1.5 专用。

- 分页查询：Everything_SetMax/SetOffset 限制单次 IPC 传输量，总数经 GetTotResults 一次获取，
  实测 29 万结果首屏 15~80ms。
- 排序：顺序式常量（1.5 服务器实测：名称 1/2、路径 3/4、大小 5/6、修改时间 13/14）。
- 看门狗：内容搜索（content:）未启用内容索引时触发实时扫描，超时后安全中止。
  注意：超时后不能调用 Everything_Reset 中止（会与卡死的 QueryW 线程争用 DLL 内部锁而永久阻塞），
  改为记录卡死线程、待其自然结束后自动恢复。
- 索引变更监听：优先 Everything_SetNotifyWindow（官方 1.5 SDK DLL 专有，放入 vendor/ 自动启用）；
  否则 5s 轻量签名轮询（offset=0, max=3）。
- 所有调用经 threading.Lock 串行化，由上层 asyncio.to_thread 放入线程池执行。
"""

from __future__ import annotations

import ctypes
import os
import threading
import time
from datetime import datetime
from typing import Any, Callable

from everytools.core.dll_loader import get_dll_loader

from csearch.types import (
    PAGE_SIZE,
    QUERY_TIMEOUT,
    ResultItem,
    SearchOutcome,
    SORT_DATE_MODIFIED_ASC,
    SORT_DATE_MODIFIED_DESC,
    SORT_NAME_ASC,
    SORT_NAME_DESC,
    SORT_PATH_ASC,
    SORT_PATH_DESC,
    SORT_SIZE_ASC,
    SORT_SIZE_DESC,
)

# 请求标志位（官方 SDK）
_REQ = (0x00000001 | 0x00000002 | 0x00000004 | 0x00000008
        | 0x00000010 | 0x00000040 | 0x00000100)

_ERR_IPC = 2            # 与 Everything 通信失败（通常 = 未运行）
_FILETIME_EPOCH = 116444736000000000
_UNKNOWN = 0xFFFFFFFFFFFFFFFF

_SORT_TABLE: dict[str, tuple[int, int]] = {
    "name": (SORT_NAME_ASC, SORT_NAME_DESC),
    "path": (SORT_PATH_ASC, SORT_PATH_DESC),
    "size": (SORT_SIZE_ASC, SORT_SIZE_DESC),
    "mtime": (SORT_DATE_MODIFIED_ASC, SORT_DATE_MODIFIED_DESC),
}

# 分类 → Everything 原生查询片段（archive: 函数在部分 1.5 配置下无效，用 ext: 列表）
_CATEGORY_QUERY: dict[str, str] = {
    "all": "", "folder": "folder:", "doc": "doc:", "pic": "pic:",
    "video": "video:", "audio": "audio:", "exe": "exe:",
    "archive": "ext:zip;rar;7z;gz;bz2;xz;tar;iso;cab;jar;war",
}

_TIME_QUERY: dict[str, str] = {
    "any": "", "today": "dm:today", "week": "dm:thisweek",
    "month": "dm:thismonth", "year": "dm:thisyear",
}


def _filetime_to_dt(value: int) -> datetime | None:
    if not value or value == _UNKNOWN:
        return None
    try:
        return datetime.fromtimestamp((value - _FILETIME_EPOCH) / 10_000_000.0)
    except (OverflowError, OSError, ValueError):
        return None


def human_size(size: int | None) -> str:
    if size is None:
        return ""
    if size < 1024:
        return f"{size} B"
    value = float(size)
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1024.0
        if value < 1024:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} PB"


def fmt_dt(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


class EngineUnavailableError(RuntimeError):
    """Everything 服务不可用（未运行 / SDK 加载失败）。"""


class SearchTimeoutError(RuntimeError):
    """查询超时（内容扫描等耗时操作），已安全中止。"""


class SearchEngine:
    """Everything SDK 客户端：分页查询 / 排序 / 索引监听。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._dll: Any = None
        self._available = False
        self._err_msg = ""
        self.version = ""
        self._stuck: threading.Thread | None = None
        self._notify_registered = False
        self._monitor_stop = threading.Event()
        self._monitor_cb: Callable[[], None] | None = None
        self._last_query: tuple[str, int] | None = None
        self._last_signature: tuple = ()
        self._init()

    # ------------------------------------------------------------------ 初始化
    def _init(self) -> None:
        try:
            loader = get_dll_loader()
            self._dll = loader.everything_dll
            self.version = loader.version
            self._setup_signatures()
            self._available = True
        except Exception as e:  # noqa: BLE001
            self._err_msg = f"Everything SDK DLL 加载失败: {e}"

    def _setup_signatures(self) -> None:
        """声明 ctypes 签名（修正 everytools 对 FullPathNameW 的错误声明）。"""
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
        d.Everything_GetResultFullPathNameW.argtypes = [ctypes.c_int, ctypes.c_wchar_p, ctypes.c_int]
        d.Everything_GetResultFullPathNameW.restype = ctypes.c_int

    # ------------------------------------------------------------------ 状态
    @property
    def available(self) -> bool:
        return self._available

    @property
    def error_message(self) -> str:
        return self._err_msg

    def check_status(self) -> tuple[bool, str, bool]:
        """检测 Everything 服务：返回 (可用, 提示信息, 索引是否已加载)。"""
        if not self._available:
            return False, self._err_msg, False
        try:
            self._ensure_ready()
            with self._lock:
                self._dll.Everything_Reset()
                self._dll.Everything_SetSearchW("")
                self._dll.Everything_SetMax(1)
                done = threading.Event()
                ok_box: list[bool] = [False]

                def _probe() -> None:
                    try:
                        ok_box[0] = bool(self._dll.Everything_QueryW(True))
                    finally:
                        done.set()

                threading.Thread(target=_probe, daemon=True).start()
                if not done.wait(timeout=10):
                    return False, "Everything 响应超时，请稍后重试", False
                if not ok_box[0]:
                    err = int(self._dll.Everything_GetLastError())
                    if err == _ERR_IPC:
                        return False, "未检测到 Everything 服务，请先启动 Everything", False
                    return False, f"Everything 查询失败（错误码 {err}）", False
                return True, "", bool(self._dll.Everything_IsDBLoaded())
        except Exception as e:  # noqa: BLE001
            return False, f"Everything 检测异常: {e}", False

    # ------------------------------------------------------------------ 查询
    @staticmethod
    def build_query(keyword: str, category: str, time_range: str, size_range: str) -> str:
        """组合 Everything 原生查询串：分类/时间/大小与关键词叠加，语法由服务端解析。"""
        parts = [p for p in (
            _CATEGORY_QUERY.get(category, ""),
            _TIME_QUERY.get(time_range, ""),
            SearchEngine._size_query(size_range),
            keyword.strip(),
        ) if p]
        return " ".join(parts)

    @staticmethod
    def _size_query(size_range: str) -> str:
        match size_range:
            case "any":
                return ""
            case "lt1mb":
                return "size:<1048576"
            case "1mb-100mb":
                return "size:1048576..104857600"
            case "100mb-1gb":
                return "size:104857600..1073741824"
            case "gt1gb":
                return "size:>1073741824"
            case custom if custom.startswith("custom:"):
                lo, _, hi = custom.split(":", 1)[1].partition(",")
                lo, hi = lo.strip(), hi.strip()
                if lo and hi:
                    return f"size:{lo}..{hi}"
                if lo:
                    return f"size:>{lo}"
                if hi:
                    return f"size:<{hi}"
                return ""
            case _:
                return ""

    @staticmethod
    def sort_value(column: str, desc: bool) -> int:
        asc, dsc = _SORT_TABLE.get(column, (SORT_NAME_ASC, SORT_NAME_DESC))
        return dsc if desc else asc

    def search(self, query: str, sort_val: int, offset: int = 0, count: int = PAGE_SIZE) -> SearchOutcome:
        """分页查询（同步，线程池内调用）。"""
        if not self._available:
            raise EngineUnavailableError(self._err_msg)
        self._ensure_ready()
        with self._lock:
            self._dll.Everything_Reset()
            self._dll.Everything_SetSearchW(query)
            self._dll.Everything_SetSort(sort_val)
            self._dll.Everything_SetRequestFlags(_REQ)
            self._dll.Everything_SetMax(count)
            self._dll.Everything_SetOffset(offset)
            done = threading.Event()
            qerr: list[Any] = []

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
                self._stuck = worker
                hint = "内容搜索需在 Everything 中启用内容索引后才会快" if "content:" in query.lower() else "请尝试更精确的关键词"
                raise SearchTimeoutError(f"搜索超时（>{QUERY_TIMEOUT:.0f}s）。{hint}")
            if not isinstance(qerr[0], bool):
                raise qerr[0]
            if not qerr[0]:
                err = int(self._dll.Everything_GetLastError())
                if err == _ERR_IPC:
                    self._available = False
                    raise EngineUnavailableError("Everything 服务已断开，请重新启动 Everything")
                raise RuntimeError(f"Everything 查询失败（错误码 {err}）")
            total = int(self._dll.Everything_GetTotResults())
            n = int(self._dll.Everything_GetNumResults())
            rows: list[ResultItem] = []
            for i in range(n):
                try:
                    rows.append(self._read_item(i))
                except Exception:  # noqa: BLE001
                    continue  # 单条读取失败跳过，不中断整体
            sig = (total, *[(r.full_path, r.mtime, r.size) for r in rows[:3]])
            self._last_query = (query, sort_val)
            self._last_signature = sig
            return SearchOutcome(rows=rows, total=total, signature=sig)

    def _read_item(self, index: int) -> ResultItem:
        d = self._dll
        name = d.Everything_GetResultFileNameW(index) or ""
        path = d.Everything_GetResultPathW(index) or ""
        is_folder = bool(d.Everything_IsFolderResult(index))
        ext = (d.Everything_GetResultExtensionW(index) or "").lower()
        size_buf = ctypes.c_ulonglong(0)
        d.Everything_GetResultSize(index, ctypes.byref(size_buf))
        size = None if size_buf.value == _UNKNOWN else int(size_buf.value)
        mtime_buf = ctypes.c_ulonglong(0)
        d.Everything_GetResultDateModified(index, ctypes.byref(mtime_buf))
        mtime = _filetime_to_dt(mtime_buf.value)
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
            is_folder=is_folder, ext=ext,
            size_str=human_size(size), date_str=fmt_dt(mtime),
        )

    def _ensure_ready(self) -> None:
        """就绪检查：卡死的查询线程结束后才允许触碰 DLL（避免并发 DLL 访问）。"""
        if self._stuck is not None:
            if self._stuck.is_alive():
                raise SearchTimeoutError("上一次查询仍在后台执行（如内容搜索扫描），请稍候重试")
            self._stuck = None

    # ------------------------------------------------------------------ 索引变更监听
    def try_register_notify_window(self, hwnd: int, msg_id: int) -> bool:
        """注册索引变更通知窗口（官方 1.5 SDK DLL 专有 API）。"""
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
        """轮询降级：每 5s 重跑最近查询（max=3）对比签名。"""
        if self._monitor_cb is not None:
            return
        self._monitor_cb = callback
        threading.Thread(target=self._monitor_loop, name="index-monitor", daemon=True).start()

    def _monitor_loop(self) -> None:
        while not self._monitor_stop.is_set():
            time.sleep(5)
            last = self._last_query
            if last is None or self._monitor_stop.is_set():
                continue
            try:
                outcome = self.search(last[0], last[1], offset=0, count=3)
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
        self._last_query = None
