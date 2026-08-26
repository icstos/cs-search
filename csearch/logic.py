"""业务编排：搜索、文件动作、书签、设置、窗口与键盘/桥事件分发。

与 UI 完全解耦：组件只调用这里的函数并传入 state，所有 SDK/系统调用
经 asyncio.to_thread 放入线程池，Flet 事件循环零阻塞。
"""

from __future__ import annotations

import asyncio
import ctypes
import ctypes.wintypes as wt
import time
from typing import Any

import flet as ft

from csearch import history, ops, store
from csearch.engine import EngineUnavailableError, SearchTimeoutError
from csearch.state import AppState, services
from csearch.tray_manager import TrayManager
from csearch.types import DEBOUNCE_MS, MAX_LOADED, PAGE_SIZE, ResultItem, WindowGeometry


def page() -> ft.Page:
    return ft.context.page


def snack(text: str) -> None:
    try:
        page().show_dialog(ft.SnackBar(ft.Text(text, size=13), duration=1800))
    except Exception:  # noqa: BLE001
        pass


def selected_items(state: AppState) -> list[ResultItem]:
    return [state.results[i] for i in sorted(state.selected) if i < len(state.results)]


def focus_search(state: AppState) -> None:
    state.focus, state.focus_epoch = "search", state.focus_epoch + 1


def focus_list(state: AppState) -> None:
    state.focus, state.focus_epoch = "list", state.focus_epoch + 1


# ==================================================================== 搜索
def on_query_changed(state: AppState, value: str) -> None:
    state.query = value
    if services._debounce is not None:
        services._debounce.cancel()
    if not value.strip():
        # 搜索框无内容：不显示搜索结果（结果区展示书签）
        state.searching, state.results, state.total = False, [], 0
        state.selected = set()
        state.last_query = ""
        return
    services._debounce = asyncio.create_task(_debounced(state))


async def _debounced(state: AppState) -> None:
    await asyncio.sleep(DEBOUNCE_MS / 1000)
    await run_search(state)


async def run_search(state: AppState, *, keep_selection: bool = False) -> None:
    if not state.engine_ok:
        ok, msg, db = await asyncio.to_thread(services.engine.check_status)
        state.engine_ok, state.engine_msg, state.index_ready = ok, msg, db
        if not ok:
            state.searching = False
            snack(msg)
            return
    query = services.engine.build_query(state.query, state.category, state.time_range, state.size_range)
    if not query.strip():
        state.searching, state.results, state.total = False, [], 0
        state.last_query = ""
        return
    seq = state.seq + 1
    state.seq, state.searching = seq, True
    sort_val = services.engine.sort_value(state.sort_col, state.sort_desc)
    t0 = time.perf_counter()
    try:
        outcome = await asyncio.to_thread(services.engine.search, query, sort_val, 0, PAGE_SIZE)
        if state.seq != seq:
            return
        counts = await asyncio.to_thread(
            history.get_counts, (r.full_path for r in outcome.rows)
        )
        for r in outcome.rows:
            r.run_count = counts.get(r.full_path, 0)
        prev = set(state.selected)
        state.results = outcome.rows
        state.total = outcome.total
        state.elapsed_ms = (time.perf_counter() - t0) * 1000
        state.searching = False
        state.last_query, state.last_sort = query, sort_val
        state.selected = {i for i in prev if i < len(state.results)} if keep_selection else set()
        state.anchor = -1 if not keep_selection else state.anchor
    except EngineUnavailableError as e:
        state.engine_ok, state.engine_msg = False, str(e)
        state.searching, state.results, state.total = False, [], 0
        snack(str(e))
    except SearchTimeoutError as e:
        state.searching, state.results, state.total = False, [], 0
        snack(str(e))
    except Exception as e:  # noqa: BLE001
        state.searching = False
        snack(f"搜索出错：{e}")


async def load_more(state: AppState) -> None:
    if state.searching or not state.last_query:
        return
    loaded = len(state.results)
    if loaded >= state.total or loaded >= MAX_LOADED:
        return
    try:
        outcome = await asyncio.to_thread(
            services.engine.search, state.last_query, state.last_sort, loaded, PAGE_SIZE
        )
    except Exception:  # noqa: BLE001
        return
    state.results = state.results + outcome.rows


async def silent_refresh(state: AppState) -> None:
    """索引变更静默刷新（去抖，保留选中）。"""
    if services._refresh is not None:
        services._refresh.cancel()
    services._refresh = asyncio.create_task(_do_refresh(state))


async def _do_refresh(state: AppState) -> None:
    await asyncio.sleep(0.8)
    if not state.searching:
        await run_search(state, keep_selection=True)


def on_sort(state: AppState, column: str) -> None:
    if column == "run_count":
        return  # 运行次数为本地数据，不参与 Everything 服务端排序
    if state.sort_col == column:
        state.sort_desc = not state.sort_desc
    else:
        state.sort_col, state.sort_desc = column, False
    asyncio.create_task(run_search(state))


def on_filter(state: AppState, field: str, value: str) -> None:
    match field:
        case "category":
            state.category = value
        case "time":
            state.time_range = value
        case "size":
            if value == "custom":
                state.size_min, state.size_max, state.dialog = "", "", "size"
                return
            state.size_range = value
        case _:
            return
    if state.query.strip():
        asyncio.create_task(run_search(state))


# ==================================================================== 选中与列表
def on_row_click(state: AppState, index: int) -> None:
    ctrl, shift = ops.modifier_state()
    if shift and state.anchor >= 0:
        lo, hi = sorted((state.anchor, index))
        state.selected = set(range(lo, hi + 1))
    elif ctrl:
        state.selected = state.selected ^ {index}  # 整体赋值触发可观测重绘
        state.anchor = index
    else:
        state.selected, state.anchor = {index}, index
    now = time.monotonic()
    if now - services._last_click_t < 0.4 and services._last_click_i == index:
        services._last_click_t = 0.0
        asyncio.create_task(open_selected(state))
    else:
        services._last_click_t, services._last_click_i = now, index


def ensure_selected(state: AppState, index: int) -> None:
    if index not in state.selected:
        state.selected, state.anchor = {index}, index


def move_selection(state: AppState, delta: int) -> None:
    if not state.results:
        return
    cur = max(state.selected) if state.selected else -1
    nxt = max(0, min(cur + delta, len(state.results) - 1))
    state.selected, state.anchor = {nxt}, nxt


def _refresh_run_counts(state: AppState, paths: list[str]) -> None:
    """打开/设置次数后本地更新 results 中的显示值（避免整表重查）。"""
    touched = set(paths)
    changed = False
    for r in state.results:
        if r.full_path in touched:
            r.run_count = history.get_counts([r.full_path]).get(r.full_path, r.run_count)
            changed = True
    if changed:
        state.results = list(state.results)  # 整体替换触发重绘


def request_run_count(state: AppState, index: int) -> None:
    """右键设置运行次数：打开输入对话框。"""
    if 0 <= index < len(state.results):
        state.run_count_path = state.results[index].full_path
        state.run_count_text = str(state.results[index].run_count)
        state.dialog = "run_count"


def confirm_run_count(state: AppState) -> None:
    """确认设置运行次数。"""
    try:
        count = max(0, int(state.run_count_text.strip() or "0"))
    except ValueError:
        snack("请输入有效的非负整数")
        return
    if not state.run_count_path:
        return
    history.set_count(state.run_count_path, count)
    _refresh_run_counts(state, [state.run_count_path])
    state.dialog = None
    snack(f"已设置运行次数：{count}")


# ==================================================================== 文件动作
async def open_selected(state: AppState) -> None:
    items = selected_items(state)
    if not items:
        snack("未选中任何文件")
        return
    errors = await asyncio.to_thread(ops.open_items, items)
    if errors:
        snack(f"打开失败：{errors[0]}")
    else:
        # 打开成功 → 运行次数 +1 并刷新当前列表显示
        opened = [i.full_path for i in items]
        await asyncio.to_thread(history.increment, opened)
        _refresh_run_counts(state, opened)


async def reveal_selected(state: AppState) -> None:
    items = selected_items(state)
    if not items:
        snack("未选中任何文件")
        return
    errors = await asyncio.to_thread(ops.reveal_items, items)
    if errors:
        snack(f"定位失败：{errors[0]}")


async def copy_paths(state: AppState) -> None:
    items = selected_items(state)
    if not items:
        snack("未选中任何文件")
        return
    error = await asyncio.to_thread(ops.copy_paths, items)
    snack(f"复制失败：{error}" if error else f"已复制 {len(items)} 个完整路径")


async def open_folder(state: AppState, index: int) -> None:
    """双击路径列：在资源管理器中打开对应文件夹。"""
    if 0 <= index < len(state.results):
        error = await asyncio.to_thread(ops.open_folder, state.results[index].path)
        if error:
            snack(f"打开文件夹失败：{error}")


async def copy_names(state: AppState) -> None:
    items = selected_items(state)
    if not items:
        snack("未选中任何文件")
        return
    error = await asyncio.to_thread(ops.copy_names, items)
    snack(f"复制失败：{error}" if error else f"已复制 {len(items)} 个文件名")


def request_delete(state: AppState) -> None:
    if selected_items(state):
        state.dialog = "delete"


async def do_delete(state: AppState, permanent: bool) -> None:
    state.dialog = None
    items = selected_items(state)
    if not items:
        return
    errors = await asyncio.to_thread(ops.delete_items, items, permanent)
    label = "永久删除" if permanent else "移入回收站"
    snack(f"已{label} {len(items) - len(errors)} 项" + (f"，失败：{errors[0]}" if errors else ""))
    await run_search(state, keep_selection=True)


def launch_everything() -> None:
    if ops.launch_everything():
        snack("正在启动 Everything…")
    else:
        import webbrowser

        webbrowser.open("https://www.voidtools.com/zh-cn/downloads/")


# ==================================================================== 书签
def open_bookmark(state: AppState) -> None:
    state.bm_edit_id, state.bm_name, state.dialog = None, (state.query.strip() or "全部文件")[:40], "bookmark"


def confirm_bookmark(state: AppState) -> None:
    store.add_bookmark(state.bookmarks, state.bm_name, state.query,
                       state.category, state.time_range, state.size_range)
    state.dialog = None
    snack("书签已保存")


def apply_bookmark(state: AppState, bm) -> None:
    state.query, state.category = bm.query, bm.category
    state.time_range, state.size_range = bm.time_range, bm.size_range
    asyncio.create_task(run_search(state))


def rename_bookmark(state: AppState, bm) -> None:
    state.bm_edit_id, state.bm_name, state.dialog = bm.id, bm.name, "bookmark"


def confirm_rename(state: AppState) -> None:
    if state.bm_edit_id:
        store.rename_bookmark(state.bookmarks, state.bm_edit_id, state.bm_name)
        state.dialog = None
        snack("书签已重命名")


def delete_bookmark(state: AppState, bm) -> None:
    store.remove_bookmark(state.bookmarks, bm.id)
    state.bookmarks = [b for b in state.bookmarks if b.id != bm.id]
    snack("书签已删除")


# ==================================================================== 设置
def open_hotkey(state: AppState) -> None:
    state.hotkey_text, state.dialog = store.load_config().hotkey, "hotkey"


def _set_hotkey(combo: str) -> bool:
    """设置全局热键（托盘未启动时不可用，返回 False 由调用方提示）。"""
    tray = services.tray
    return tray.set_hotkey(combo) if tray is not None else False


def confirm_hotkey(state: AppState) -> None:
    combo = state.hotkey_text.strip().lower()
    if combo:
        if not _set_hotkey(combo):
            snack("热键注册失败，请更换组合（如 alt+space / ctrl+shift+f）")
            return
    else:
        _set_hotkey("")  # 空 = 禁用
    store.save_hotkey(combo)
    state.dialog = None
    snack(f"全局热键已更新：{combo or '（已禁用）'}")


def confirm_size(state: AppState) -> None:
    def to_bytes(text: str) -> int | None:
        text = text.strip()
        if not text:
            return None
        try:
            value = float(text)
            return int(value * 1024 * 1024) if value >= 0 else None
        except ValueError:
            return None

    lo, hi = to_bytes(state.size_min), to_bytes(state.size_max)
    if lo is None and hi is None:
        state.dialog = None
        return
    if lo is not None and hi is not None and lo > hi:
        snack("最小不能大于最大")
        return
    state.size_range = f"custom:{lo or ''},{hi or ''}"
    state.dialog = None
    asyncio.create_task(run_search(state))


# ==================================================================== 列宽拖拽
_MIN_COL = {"name": 80, "path": 100, "size": 60, "mtime": 80, "run_count": 50}


def start_col_drag_gesture(state: AppState, col: str, e: Any) -> None:
    """GestureDetector 拖拽开始：记录起始宽度与指针全局位置。"""
    if state.drag_col is not None:
        return
    state.drag_col = col
    services._drag_start = state.col_widths.get(col, 100)
    services._drag_origin = getattr(getattr(e, "global_position", None), "dx", None)


def update_col_drag_gesture(state: AppState, col: str, e: Any) -> None:
    """拖拽中：按 global_position 与起点的差值（逻辑像素）更新列宽。"""
    if state.drag_col != col or services._drag_origin is None:
        return
    gx = getattr(getattr(e, "global_position", None), "dx", None)
    if gx is None:
        return
    width = max(_MIN_COL.get(col, 60), min(int(services._drag_start + gx - services._drag_origin), 900))
    if width != state.col_widths.get(col):
        state.col_widths = {**state.col_widths, col: width}


def end_col_drag_gesture(state: AppState) -> None:
    state.drag_col = None


def _cursor_x() -> int:
    try:
        pt = wt.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return int(pt.x)
    except Exception:  # noqa: BLE001
        return 0


def _mouse_down() -> bool:
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
    except Exception:  # noqa: BLE001
        return False


def _dpi_scale() -> float:
    try:
        hwnd = ctypes.windll.user32.FindWindowW(None, "CSearch - 极速文件搜索")
        rect = wt.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        logical = float(page().window.width or 1040)
        return (rect.right - rect.left) / logical if logical else 1.0
    except Exception:  # noqa: BLE001
        return 1.0


async def start_col_drag(state: AppState, col: str) -> None:
    """表头列宽拖拽：按下分隔条后轮询鼠标位置，松开左键结束。

    flet 0.86.5 的 GestureDetector 水平拖拽事件数据不可靠（delta 常为 None，
    导致宽度不更新），改用 GetCursorPos 轮询，与 UI 框架无关，稳定可用。
    """
    if state.drag_col is not None:
        return
    state.drag_col = col
    state.row_width_snap = dict(state.col_widths)  # 拖拽起点行快照
    start_x, start_w = _cursor_x(), state.col_widths.get(col, 100)
    scale = _dpi_scale()
    frame = 0
    try:
        while _mouse_down():
            width = max(_MIN_COL.get(col, 60), min(int(start_w + (_cursor_x() - start_x) / scale), 900))
            if abs(width - state.col_widths.get(col, 100)) >= 1:  # 1px 灵敏度，避免抖动提交
                state.col_widths = {**state.col_widths, col: width}
            frame += 1
            if frame % 5 == 0:
                # 节流：行控件每 60ms 重排一次（表头每帧跟手，行低频重排保证流畅）
                state.row_width_snap = dict(state.col_widths)
            await asyncio.sleep(0.012)
    finally:
        state.row_width_snap = dict(state.col_widths)  # 松手后行对齐最终宽度
        state.drag_col = None


def adapt_columns(state: AppState) -> None:
    """窗口缩放时按比例适配弹性列（名称/路径），固定列（大小/时间）不变。"""
    p = page()
    try:
        total = float(p.window.width or 1040)
        fixed = (state.col_widths.get("size", 90) + state.col_widths.get("mtime", 140)
                 + state.col_widths.get("run_count", 70) + 40)
        flexible = max(240.0, total - fixed)
        ratio = flexible / (state.col_widths.get("name", 260) + state.col_widths.get("path", 420))
        name = max(_MIN_COL["name"], int(state.col_widths.get("name", 260) * ratio))
        path = max(_MIN_COL["path"], int(state.col_widths.get("path", 420) * ratio))
        if (name, path) != (state.col_widths.get("name"), state.col_widths.get("path")):
            state.col_widths = {**state.col_widths, "name": name, "path": path}
    except Exception:  # noqa: BLE001
        pass


# ==================================================================== 窗口 / 键盘 / 桥事件
class _MonitorInfo(ctypes.Structure):
    """MONITORINFO（ctypes.wintypes 未内置，需自行定义）。"""

    _fields_ = [
        ("cbSize", wt.DWORD),
        ("rcMonitor", wt.RECT),
        ("rcWork", wt.RECT),
        ("dwFlags", wt.DWORD),
    ]


def _work_areas() -> list[tuple[int, int, int, int]]:
    """所有显示器工作区（物理像素）(left, top, right, bottom)；失败返回空列表。"""
    areas: list[tuple[int, int, int, int]] = []
    try:
        user32 = ctypes.windll.user32

        @ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.POINTER(wt.RECT), ctypes.c_void_p,
        )
        def _enum(hmon, hdc, lprect, lparam):
            mi = _MonitorInfo()
            mi.cbSize = ctypes.sizeof(_MonitorInfo)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                areas.append((mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom))
            return True

        user32.EnumDisplayMonitors(None, None, _enum, None)
    except Exception:  # noqa: BLE001
        return []
    return areas


def _ensure_window_on_screen() -> None:
    """窗口位置防跑出屏幕：多显示器布局变化导致保存的坐标失效时，窗口主体可能
    落在屏幕外（任务栏有程序、界面却看不到）。若窗口与所有显示器工作区的交集
    小于窗口面积的 25%，将其移回交集最大的显示器并居中/贴边。"""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "CSearch - 极速文件搜索")
        if not hwnd:
            return
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return
        areas = _work_areas()
        if not areas:
            return
        best: tuple[int, int, int, int, int] | None = None  # (面积, l, t, r, b)
        for l, t, r, b in areas:
            iw = max(0, min(rect.right, r) - max(rect.left, l))
            ih = max(0, min(rect.bottom, b) - max(rect.top, t))
            area = iw * ih
            if best is None or area > best[0]:
                best = (area, l, t, r, b)
        if best is None or best[0] >= width * height * 0.25:
            return  # 主体可见，无需纠正
        _, wl, wtop, wr, wbottom = best
        # 窗口比工作区大时贴边，否则居中；保证标题栏落在屏内
        new_left = wl if width >= wr - wl else wl + (wr - wl - width) // 2
        new_top = wtop if height >= wbottom - wtop else wtop + (wbottom - wtop - height) // 2
        user32.SetWindowPos(
            hwnd, None, new_left, new_top, 0, 0,
            0x0001 | 0x0004 | 0x0010,  # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
        )
    except Exception:  # noqa: BLE001
        pass


async def _ensure_window_on_screen_later() -> None:
    """启动延迟兜底：等客户端应用完保存的窗口几何后再校验屏幕内位置。"""
    await asyncio.sleep(0.6)
    _ensure_window_on_screen()


def _force_foreground_windows(title: str) -> None:
    """Windows 前台锁定规避：托盘/热键唤回时，SetForegroundWindow 可能被系统拒绝
    （进程未收到输入事件），导致窗口显示但无键盘焦点、无法直接输入。
    经典做法：先模拟一次 Alt 键按下/释放，再 SetForegroundWindow + SetFocus。"""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            return
        user32.keybd_event(0x12, 0, 0, 0)  # VK_MENU down
        user32.keybd_event(0x12, 0, 2, 0)  # VK_MENU up
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
    except Exception:  # noqa: BLE001
        pass


async def show_window(state: AppState) -> None:
    p = page()
    try:
        p.window.visible, p.window.minimized = True, False
        p.update()
        # 唤醒时同步纠正屏幕外位置（多显示器布局变化后保存的坐标可能失效）
        _ensure_window_on_screen()
        # to_front 是协程：必须 await，否则窗口不会置顶且产生 RuntimeWarning
        await p.window.to_front()
    except Exception:  # noqa: BLE001
        pass
    # 托盘/热键唤回：强制获得 OS 键盘焦点（Windows 前台锁定兜底）
    _force_foreground_windows(p.title)
    focus_search(state)


def hide_to_tray(state: AppState) -> None:
    p = page()
    try:
        p.window.visible = False
        p.update()
    except Exception:  # noqa: BLE001
        pass
    if not state.balloon_shown and services.tray is not None:
        state.balloon_shown = True
        services.tray.notify("已最小化到系统托盘，全局热键可再次唤起", "CSearch")


async def toggle_window(state: AppState) -> None:
    if page().window.visible:
        hide_to_tray(state)
    else:
        await show_window(state)


def _save_geometry() -> None:
    p = page()
    try:
        geo = store.load_config().window
        geo.width = max(760, int(p.window.width or geo.width))
        geo.height = max(480, int(p.window.height or geo.height))
        if p.window.left is not None:
            geo.left = int(p.window.left)
        if p.window.top is not None:
            geo.top = int(p.window.top)
        geo.maximized = bool(p.window.maximized)
        store.save_window(geo)
    except Exception:  # noqa: BLE001
        pass


def on_window_event(state: AppState | None, e: Any) -> None:
    if state is None:
        return
    # e.type 是 WindowEventType 枚举：用 .value（如 "close"）比较，str(枚举) 是 "WindowEventType.CLOSE" 永远匹配不上
    match getattr(e, "type", None):
        case ft.WindowEventType.CLOSE if not state.quitting:
            hide_to_tray(state)
        case ft.WindowEventType.SHOW:
            focus_search(state)
        case ft.WindowEventType.RESTORE:
            # 最小化 → 恢复（任务栏/Alt+Tab 唤回）同样需要抢回搜索框焦点
            focus_search(state)
        case ft.WindowEventType.RESIZED | ft.WindowEventType.MOVED:
            adapt_columns(state)
            if services._geo is not None:
                services._geo.cancel()

            async def _do() -> None:
                await asyncio.sleep(0.6)
                _save_geometry()

            services._geo = asyncio.create_task(_do())


async def quit_app(state: AppState) -> None:
    if state.quitting:
        return
    state.quitting = True
    _save_geometry()
    # 退出顺序：停止热键监听 → 销毁托盘实例（TrayManager.stop 内部按序执行）→ 关闭主程序
    if services.tray is not None:
        services.tray.stop()
        services.tray = None
    services.engine.stop_change_monitor()
    p = page()
    try:
        p.window.prevent_close = False
        # destroy 是协程：必须 await，否则窗口不关闭且产生 RuntimeWarning
        await p.window.destroy()
    except Exception:  # noqa: BLE001
        import os

        os._exit(0)


async def on_keyboard(state: AppState | None, e: Any) -> None:
    if state is None:
        return
    key, ctrl = str(getattr(e, "key", "") or "").lower(), bool(getattr(e, "ctrl", False))
    match (ctrl, key):
        case (False, "f5"):
            await run_search(state, keep_selection=True)
        case (True, "d"):
            await copy_paths(state)
        case (True, "e"):
            await reveal_selected(state)
        case (True, "a"):
            state.selected, state.anchor = set(range(len(state.results))), 0
        case (False, "escape") if state.focus == "list":
            focus_search(state)
        case (False, "escape"):
            state.query = ""
            focus_search(state)
        case (False, "arrowdown") if state.focus == "search" and state.results:
            state.selected, state.anchor = {0}, 0
            focus_list(state)


async def on_list_key(state: AppState, key: str) -> None:
    match str(key or "").lower():
        case "arrowdown":
            move_selection(state, 1)
        case "arrowup":
            move_selection(state, -1)
        case "enter":
            await open_selected(state)
        case "escape":
            focus_search(state)


async def init_app(state: AppState) -> None:
    import os

    # 启动后延迟校验窗口位置：多显示器布局变化时保存的坐标可能已失效（窗口落在
    # 屏幕外 → 任务栏有程序但界面看不到），此时把窗口移回可见区域。
    asyncio.create_task(_ensure_window_on_screen_later())
    await asyncio.to_thread(history.init_db)
    ok, msg, db = await asyncio.to_thread(services.engine.check_status)
    state.engine_ok, state.engine_msg, state.index_ready = ok, msg, db
    state.engine_version = services.engine.version
    state.bookmarks = store.load_bookmarks()
    try:
        services.tray = TrayManager(
            title="CSearch - 极速文件搜索",
            hotkey=store.load_config().hotkey,
            on_toggle=lambda: services.bridge.emit("toggle"),
            on_show=lambda: services.bridge.emit("show"),
            on_hide=lambda: services.bridge.emit("hide"),
            on_quit=lambda: services.bridge.emit("quit"),
        )
        services.tray.start()
    except Exception:  # noqa: BLE001
        services.tray = None
    if not services.engine.notify_registered:
        services.engine.start_change_monitor(lambda: services.bridge.emit("index_changed"))
    # 支持启动即搜索（环境变量 CSEARCH_QUERY；默认空 = 不搜索，展示书签面板）
    init_query = os.environ.get("CSEARCH_QUERY", "").strip()
    if init_query:
        state.query = init_query
    await run_search(state)


async def bridge_loop(state: AppState) -> None:
    while True:
        ev = await services.bridge.next()
        if ev is None:
            continue
        match ev["type"]:
            case "toggle":
                await toggle_window(state)
            case "show":
                await show_window(state)
            case "hide":
                hide_to_tray(state)
            case "quit":
                await quit_app(state)
                return
            case "index_changed":
                await silent_refresh(state)
