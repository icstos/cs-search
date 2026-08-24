"""业务编排层：防抖搜索、懒加载、静默刷新、文件操作动作、书签/热键/窗口管理。

UI 层只负责声明式渲染与事件转发，所有业务逻辑集中于此，与界面完全解耦。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import flet as ft

from csearch import file_ops
from csearch.logger import get_logger
from csearch.search_engine import (
    ContentSearchUnsupportedError,
    EngineUnavailableError,
    ResultItem,
    SearchTimeoutError,
)
from csearch.state import DEBOUNCE_MS, MAX_LOADED, PAGE_SIZE, AppState, Services, services


# ==================================================================== 基础工具
def snack(page: ft.Page, msg: str) -> None:
    """轻量 SnackBar 提示（页面级副作用）。"""
    try:
        page.show_dialog(
            ft.SnackBar(
                ft.Text(msg, size=13),
                duration=1800,
                behavior=ft.SnackBarBehavior.FLOATING,
            )
        )
    except Exception:  # noqa: BLE001
        pass


def selected_items(state: AppState) -> list[ResultItem]:
    return [state.results[i] for i in sorted(state.selected) if i < len(state.results)]


def focus_search(state: AppState) -> None:
    state.focus_target = "search"
    state.focus_epoch += 1


def focus_list(state: AppState) -> None:
    state.focus_target = "list"
    state.focus_epoch += 1


# ==================================================================== 搜索
def on_query_changed(state: AppState, page: ft.Page, value: str) -> None:
    """搜索框输入：300ms 防抖后触发搜索。"""
    state.query = value
    if services._debounce is not None:
        services._debounce.cancel()
    services._debounce = asyncio.create_task(_debounced_search(state, page))


async def _debounced_search(state: AppState, page: ft.Page) -> None:
    await asyncio.sleep(DEBOUNCE_MS / 1000)
    await run_search(state, page, reset=True)


async def run_search(
    state: AppState,
    page: ft.Page,
    reset: bool = True,
    keep_selection: bool = False,
) -> None:
    """核心搜索流程：线程池执行 SDK 调用（不阻塞事件循环），带竞态防护。"""
    log = get_logger()
    if not state.engine_ok:
        ok, msg, db = await asyncio.to_thread(services.engine.check_status)
        state.engine_ok, state.engine_msg, state.index_ready = ok, msg, db
        if not ok:
            state.searching = False
            snack(page, msg)
            log.warning("run_search: engine unavailable: %s", msg)
            return

    seq = state.query_seq + 1
    state.query_seq = seq
    state.searching = True
    query = services.engine.build_query(state.query, state.category, state.time_range, state.size_range)
    sort_val = services.engine.sort_value(state.sort_col, state.sort_desc)
    log.info("run_search start seq=%d query=%r sort=%d", seq, query, sort_val)
    t0 = time.perf_counter()
    try:
        async with services.search_lock:
            log.info("run_search: lock acquired, submitting to thread")
            outcome = await asyncio.to_thread(
                services.engine.search, query, sort_val, 0, PAGE_SIZE
            )
            log.info("run_search: search done rows=%d total=%d", len(outcome.rows), outcome.total)
        if state.query_seq != seq:
            return  # 已有更新的查询，丢弃本次过期结果
        prev_selected = set(state.selected)
        state.results = outcome.rows
        state.total = outcome.total
        state.total_files = outcome.total_files
        state.total_folders = outcome.total_folders
        state.loaded = len(outcome.rows)
        state.elapsed_ms = (time.perf_counter() - t0) * 1000
        state.searching = False
        state.last_query_str = query
        state.last_sort_val = sort_val
        log.info("run_search: state applied seq=%d", seq)
        if keep_selection:
            state.selected = {i for i in prev_selected if i < len(state.results)}
        else:
            state.selected = set()
            state.select_anchor = -1
    except EngineUnavailableError as e:
        log.warning("run_search: unavailable: %s", e)
        state.engine_ok = False
        state.engine_msg = str(e)
        state.searching = False
        state.results, state.total = [], 0
        snack(page, str(e))
    except (SearchTimeoutError, ContentSearchUnsupportedError) as e:
        log.warning("run_search: %s", e)
        state.searching = False
        state.results, state.total = [], 0
        snack(page, str(e))
    except Exception as e:  # noqa: BLE001
        log.exception("run_search: unexpected error")
        state.searching = False
        snack(page, f"搜索出错：{e}")


async def load_more(state: AppState, page: ft.Page) -> None:
    """滚动触底增量加载（懒加载核心：控制单次渲染规模）。"""
    if state.searching:
        return
    loaded = len(state.results)
    if loaded >= state.total or loaded >= MAX_LOADED:
        return
    if not state.last_query_str:
        return
    try:
        outcome = await asyncio.to_thread(
            services.engine.search, state.last_query_str, state.last_sort_val, loaded, PAGE_SIZE
        )
    except Exception:  # noqa: BLE001
        return
    state.results = state.results + outcome.rows
    state.loaded = len(state.results)


async def silent_refresh(state: AppState, page: ft.Page) -> None:
    """索引变更后的静默刷新：保留选中状态、不打断操作（带 800ms 去抖）。"""
    if services._refresh_task is not None:
        services._refresh_task.cancel()
    services._refresh_task = asyncio.create_task(_do_silent_refresh(state, page))


async def _do_silent_refresh(state: AppState, page: ft.Page) -> None:
    await asyncio.sleep(0.8)
    if state.searching:
        return
    if not state.engine_ok:
        await run_search(state, page, reset=False)
        return
    await run_search(state, page, reset=False, keep_selection=True)


def on_sort(state: AppState, page: ft.Page, column: str) -> None:
    """表头点击：同列切换升降序，不同列切到该列升序。"""
    if state.sort_col == column:
        state.sort_desc = not state.sort_desc
    else:
        state.sort_col = column
        state.sort_desc = False
    asyncio.create_task(run_search(state, page, reset=True))


def on_category_changed(state: AppState, page: ft.Page, value: str) -> None:
    state.category = value
    asyncio.create_task(run_search(state, page, reset=True))


def on_time_changed(state: AppState, page: ft.Page, value: str) -> None:
    state.time_range = value
    asyncio.create_task(run_search(state, page, reset=True))


def on_size_changed(state: AppState, page: ft.Page, value: str) -> None:
    if value == "custom":
        open_size_dialog(state)
        return
    state.size_range = value
    asyncio.create_task(run_search(state, page, reset=True))


# ==================================================================== 选中与列表
def on_row_click(state: AppState, page: ft.Page, idx: int) -> None:
    """行点击：单选 / Ctrl 多选 / Shift 范围多选；双击打开。"""
    ctrl, shift = file_ops.modifier_state()
    if shift and state.select_anchor >= 0:
        lo, hi = sorted((state.select_anchor, idx))
        state.selected = set(range(lo, hi + 1))
    elif ctrl:
        sel = set(state.selected)
        if idx in sel:
            sel.discard(idx)
        else:
            sel.add(idx)
        state.selected = sel
        state.select_anchor = idx
    else:
        state.selected = {idx}
        state.select_anchor = idx
    # 双击检测 → 打开
    now = time.monotonic()
    if now - services._last_click_t < 0.4 and services._last_click_idx == idx:
        services._last_click_t = 0.0
        asyncio.create_task(open_selected(page, state))
    else:
        services._last_click_t = now
        services._last_click_idx = idx


def ensure_selected(state: AppState, idx: int) -> None:
    """右键菜单动作前：若该行不在选中集，则单选该行（Everything 行为）。"""
    if idx not in state.selected:
        state.selected = {idx}
        state.select_anchor = idx


def move_selection(state: AppState, delta: int) -> None:
    if not state.results:
        return
    cur = max(state.selected) if state.selected else -1
    nxt = cur + delta
    nxt = max(0, min(nxt, len(state.results) - 1))
    state.selected = {nxt}
    state.select_anchor = nxt


# ==================================================================== 文件操作
async def open_selected(page: ft.Page, state: AppState) -> None:
    items = selected_items(state)
    if not items:
        snack(page, "未选中任何文件")
        return
    ok, errs = await asyncio.to_thread(file_ops.open_items, items)
    if errs:
        snack(page, f"打开失败：{errs[0]}")


async def reveal_selected(page: ft.Page, state: AppState) -> None:
    items = selected_items(state)
    if not items:
        snack(page, "未选中任何文件")
        return
    ok, errs = await asyncio.to_thread(file_ops.reveal_items, items)
    if errs:
        snack(page, f"定位失败：{errs[0]}")


async def copy_paths(page: ft.Page, state: AppState) -> None:
    items = selected_items(state)
    if not items:
        snack(page, "未选中任何文件")
        return
    n, err = await asyncio.to_thread(file_ops.copy_paths, items)
    if err:
        snack(page, f"复制失败：{err}")
    else:
        snack(page, f"已复制 {n} 个完整路径")


async def copy_names(page: ft.Page, state: AppState) -> None:
    items = selected_items(state)
    if not items:
        snack(page, "未选中任何文件")
        return
    n, err = await asyncio.to_thread(file_ops.copy_names, items)
    if err:
        snack(page, f"复制失败：{err}")
    else:
        snack(page, f"已复制 {n} 个文件名")


def request_delete(state: AppState) -> None:
    if not selected_items(state):
        snack(ft.context.page, "未选中任何文件")
        return
    state.dlg_delete = True


async def do_delete(page: ft.Page, state: AppState, permanent: bool) -> None:
    state.dlg_delete = False
    items = selected_items(state)
    if not items:
        return
    ok, errs = await asyncio.to_thread(file_ops.delete_items, items, permanent)
    label = "永久删除" if permanent else "移入回收站"
    if errs:
        snack(page, f"{label} {ok} 项，失败：{errs[0]}")
    else:
        snack(page, f"已{label} {ok} 项")
    await run_search(state, page, reset=False, keep_selection=True)


# ==================================================================== 书签
def open_bookmark_dialog(state: AppState) -> None:
    state.bookmark_edit_id = None
    state.bm_name = (state.query.strip() or "全部文件")[:40]
    state.dlg_bookmark = True


def confirm_bookmark(page: ft.Page, state: AppState) -> None:
    services.bookmarks.add(state.bm_name, state.query, state.category, state.time_range, state.size_range)
    state.bookmarks = services.bookmarks.all()
    state.dlg_bookmark = False
    snack(page, "书签已保存")


def apply_bookmark(page: ft.Page, state: AppState, bm: dict[str, Any]) -> None:
    state.query = bm.get("query", "")
    state.category = bm.get("category", "all")
    state.time_range = bm.get("time_range", "any")
    state.size_range = bm.get("size_range", "any")
    asyncio.create_task(run_search(state, page, reset=True))


def rename_bookmark(state: AppState, bm: dict[str, Any]) -> None:
    state.bookmark_edit_id = bm["id"]
    state.bm_name = bm.get("name", "")
    state.dlg_bookmark = True


def confirm_rename(page: ft.Page, state: AppState) -> None:
    if state.bookmark_edit_id:
        services.bookmarks.rename(state.bookmark_edit_id, state.bm_name)
        state.bookmarks = services.bookmarks.all()
        state.dlg_bookmark = False
        snack(page, "书签已重命名")


def delete_bookmark(page: ft.Page, state: AppState, bm: dict[str, Any]) -> None:
    services.bookmarks.remove(bm["id"])
    state.bookmarks = services.bookmarks.all()
    snack(page, "书签已删除")


# ==================================================================== 热键 / 大小区间
def open_hotkey_dialog(state: AppState) -> None:
    state.hk_text = services.config.get_hotkey()
    state.dlg_hotkey = True


def confirm_hotkey(page: ft.Page, state: AppState) -> None:
    combo = state.hk_text.strip().lower()
    if combo:
        ok = services.hotkey.set_hotkey(combo)
        if not ok:
            snack(page, "热键注册失败，请更换组合（如 alt+space / ctrl+shift+f）")
            return
    else:
        services.hotkey.set_hotkey("")  # 空 = 禁用
    services.config.set_hotkey(combo)
    state.dlg_hotkey = False
    snack(page, f"全局热键已更新：{combo or '（已禁用）'}")


def open_size_dialog(state: AppState) -> None:
    state.size_min, state.size_max = "", ""
    state.dlg_size = True


def confirm_size(page: ft.Page, state: AppState) -> None:
    lo = _parse_mb(state.size_min)
    hi = _parse_mb(state.size_max)
    if lo is None and hi is None:
        state.dlg_size = False
        return
    if lo is not None and hi is not None and lo > hi:
        snack(page, "最小不能大于最大")
        return
    state.size_range = f"custom:{int(lo) if lo else ''},{int(hi) if hi else ''}"
    state.dlg_size = False
    asyncio.create_task(run_search(state, page, reset=True))


def _parse_mb(text: str) -> Optional[int]:
    text = text.strip()
    if not text:
        return None
    try:
        val = float(text)
        if val < 0:
            return None
        return int(val * 1024 * 1024)
    except ValueError:
        return None


# ==================================================================== 窗口 / 热键事件
def show_window(page: ft.Page, state: AppState) -> None:
    try:
        page.window.visible = True
        page.window.minimized = False
        page.update()
        page.window.to_front()
    except Exception:  # noqa: BLE001
        pass
    focus_search(state)


def hide_to_tray(page: ft.Page, state: AppState) -> None:
    try:
        page.window.visible = False
        page.update()
    except Exception:  # noqa: BLE001
        pass
    if not services._balloon_shown:
        services._balloon_shown = True
        try:
            if services.tray is not None:
                services.tray.show_balloon("CSearch", "已最小化到系统托盘，全局热键可再次唤起")
        except Exception:  # noqa: BLE001
            pass


def toggle_window(page: ft.Page, state: AppState) -> None:
    if page.window.visible:
        hide_to_tray(page, state)
    else:
        show_window(page, state)


async def quit_app(page: ft.Page, state: AppState) -> None:
    """退出：保存配置 → 停止热键/托盘/监听 → 销毁窗口。"""
    if services.quitting:
        return
    services.quitting = True
    _save_geometry(page)
    try:
        services.hotkey.stop()
    except Exception:  # noqa: BLE001
        pass
    try:
        services.tray.stop_tray()
    except Exception:  # noqa: BLE001
        pass
    services.engine.stop_change_monitor()
    try:
        page.window.prevent_close = False
        page.window.destroy()
    except Exception:  # noqa: BLE001
        import os

        os._exit(0)


def on_window_event(page: ft.Page, state: Optional[AppState], e: Any) -> None:
    """窗口事件：关闭→托盘；显示→聚焦搜索框；移动/缩放→记忆几何。"""
    if state is None:
        return
    t = str(getattr(e, "type", "")).lower()
    if t == "close":
        if not services.quitting:
            hide_to_tray(page, state)
    elif t == "show":
        focus_search(state)
    elif t in ("resized", "moved"):
        _schedule_geometry_save(page)


def _schedule_geometry_save(page: ft.Page) -> None:
    if services._geo_task is not None:
        services._geo_task.cancel()

    async def _do():
        await asyncio.sleep(0.6)
        _save_geometry(page)

    services._geo_task = asyncio.create_task(_do())


def _save_geometry(page: ft.Page) -> None:
    try:
        geo = services.config.get_window()
        geo.width = max(760, int(page.window.width or geo.width))
        geo.height = max(480, int(page.window.height or geo.height))
        if page.window.left is not None:
            geo.left = int(page.window.left)
        if page.window.top is not None:
            geo.top = int(page.window.top)
        geo.maximized = bool(page.window.maximized)
        services.config.set_window(geo)
    except Exception:  # noqa: BLE001
        pass


async def on_page_keyboard(page: ft.Page, state: Optional[AppState], e: Any) -> None:
    """页面级快捷键：F5 / Ctrl+D / Ctrl+E / Ctrl+A / Esc / ↓（搜索框→列表）。"""
    if state is None:
        return
    key = str(getattr(e, "key", "") or "").lower()
    ctrl = bool(getattr(e, "ctrl", False))
    if key == "f5":
        await run_search(state, page, reset=False, keep_selection=True)
    elif ctrl and key == "d":
        await copy_paths(page, state)
    elif ctrl and key == "e":
        await reveal_selected(page, state)
    elif ctrl and key == "a":
        state.selected = set(range(len(state.results)))
        state.select_anchor = 0
    elif key == "escape":
        if state.focus_target == "list":
            focus_search(state)
        else:
            state.query = ""
            focus_search(state)
    elif key == "arrowdown" and state.focus_target == "search" and state.results:
        state.selected = {0}
        state.select_anchor = 0
        focus_list(state)


async def on_list_key(state: AppState, page: ft.Page, key: str) -> None:
    """结果列表按键（KeyboardListener）：↑/↓/Enter/Esc。"""
    k = str(key or "").lower()
    if k == "arrowdown":
        move_selection(state, 1)
    elif k == "arrowup":
        move_selection(state, -1)
    elif k == "enter":
        await open_selected(page, state)
    elif k == "escape":
        focus_search(state)


# ==================================================================== 初始化 / 事件桥
async def init_app(page: ft.Page, state: AppState) -> None:
    """启动初始化：引擎检测 → 书签加载 → 托盘/热键/索引监听 → 首屏搜索。"""
    log = get_logger()
    log.info("init_app begin")
    ok, msg, db = await asyncio.to_thread(services.engine.check_status)
    log.info("init_app: engine ok=%s db=%s msg=%s", ok, db, msg)
    state.engine_ok, state.engine_msg, state.index_ready = ok, msg, db
    state.engine_version = services.engine.version
    state.bookmarks = services.bookmarks.all()

    from csearch.hotkey_tray import HotkeyManager, TrayManager

    try:
        services.tray = TrayManager(services.bridge, services.engine.try_register_notify_window)
        services.tray.start_tray()
    except Exception:  # noqa: BLE001
        services.tray = None
    try:
        services.hotkey = HotkeyManager(services.bridge)
        services.hotkey.set_hotkey(services.config.get_hotkey())
    except Exception:  # noqa: BLE001
        services.hotkey = None
    # 通知窗口不可用时降级为 5s 签名轮询
    if not services.engine.notify_registered:
        services.engine.start_change_monitor(lambda: services.bridge.put({"type": "index_changed"}))

    if services.config.is_first_run():
        snack(page, "提示：关闭窗口将最小化到系统托盘，Alt+Space 随时唤起")
    services.config.mark_started()
    await run_search(state, page, reset=True)
    log.info("init_app end")


async def bridge_loop(state: AppState, page: ft.Page) -> None:
    """消费热键/托盘/索引通知线程事件（跨线程安全）。"""
    log = get_logger()
    log.info("bridge_loop start")
    while True:
        ev = await services.bridge.get(0.3)
        if ev is None:
            continue
        t = ev.get("type")
        try:
            if t == "toggle":
                toggle_window(page, state)
            elif t == "show":
                show_window(page, state)
            elif t == "quit":
                await quit_app(page, state)
                return
            elif t == "index_changed":
                await silent_refresh(state, page)
        except Exception:  # noqa: BLE001
            continue
