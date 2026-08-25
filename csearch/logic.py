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

from csearch import ops, store
from csearch.engine import EngineUnavailableError, SearchTimeoutError
from csearch.state import AppState, services
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


# ==================================================================== 文件动作
async def open_selected(state: AppState) -> None:
    items = selected_items(state)
    if not items:
        snack("未选中任何文件")
        return
    errors = await asyncio.to_thread(ops.open_items, items)
    if errors:
        snack(f"打开失败：{errors[0]}")


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


def confirm_hotkey(state: AppState) -> None:
    combo = state.hotkey_text.strip().lower()
    if combo:
        if not services.hotkey.set(combo):
            snack("热键注册失败，请更换组合（如 alt+space / ctrl+shift+f）")
            return
    else:
        services.hotkey.set("")  # 空 = 禁用
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
_MIN_COL = {"name": 80, "path": 100, "size": 60, "mtime": 80}


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
    print(f"[drag] start col={col}", flush=True)
    state.drag_col = col
    start_x, start_w = _cursor_x(), state.col_widths.get(col, 100)
    scale = _dpi_scale()
    try:
        while _mouse_down():
            width = max(_MIN_COL.get(col, 60), min(int(start_w + (_cursor_x() - start_x) / scale), 900))
            if width % 40 == 0:
                print(f"[drag] width={width}", flush=True)
            if width != state.col_widths.get(col):
                state.col_widths = {**state.col_widths, col: width}
            await asyncio.sleep(0.016)
    finally:
        state.drag_col = None


def adapt_columns(state: AppState) -> None:
    """窗口缩放时按比例适配弹性列（名称/路径），固定列（大小/时间）不变。"""
    p = page()
    try:
        total = float(p.window.width or 1040)
        fixed = state.col_widths.get("size", 90) + state.col_widths.get("mtime", 140) + 40
        flexible = max(240.0, total - fixed)
        ratio = flexible / (state.col_widths.get("name", 260) + state.col_widths.get("path", 420))
        name = max(_MIN_COL["name"], int(state.col_widths.get("name", 260) * ratio))
        path = max(_MIN_COL["path"], int(state.col_widths.get("path", 420) * ratio))
        if (name, path) != (state.col_widths.get("name"), state.col_widths.get("path")):
            state.col_widths = {**state.col_widths, "name": name, "path": path}
    except Exception:  # noqa: BLE001
        pass


# ==================================================================== 窗口 / 键盘 / 桥事件
def show_window(state: AppState) -> None:
    p = page()
    try:
        p.window.visible, p.window.minimized = True, False
        p.update()
        p.window.to_front()
    except Exception:  # noqa: BLE001
        pass
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
        services.tray.balloon("CSearch", "已最小化到系统托盘，全局热键可再次唤起")


def toggle_window(state: AppState) -> None:
    if page().window.visible:
        hide_to_tray(state)
    else:
        show_window(state)


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
    match str(getattr(e, "type", "")).lower():
        case "close" if not state.quitting:
            hide_to_tray(state)
        case "show":
            focus_search(state)
        case "resized" | "moved":
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
    services.hotkey.stop()
    if services.tray is not None:
        services.tray.stop_tray()
    services.engine.stop_change_monitor()
    p = page()
    try:
        p.window.prevent_close = False
        p.window.destroy()
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

    ok, msg, db = await asyncio.to_thread(services.engine.check_status)
    state.engine_ok, state.engine_msg, state.index_ready = ok, msg, db
    state.engine_version = services.engine.version
    state.bookmarks = store.load_bookmarks()
    try:
        services.tray = TrayManager(services.bridge, services.engine.try_register_notify_window)
        services.tray.start_tray()
    except Exception:  # noqa: BLE001
        services.tray = None
    services.hotkey.set(store.load_config().hotkey)
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
                toggle_window(state)
            case "show":
                show_window(state)
            case "quit":
                await quit_app(state)
                return
            case "index_changed":
                await silent_refresh(state)
