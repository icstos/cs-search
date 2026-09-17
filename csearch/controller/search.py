"""搜索编排：防抖输入、分页查询、增量加载、静默刷新、排序/过滤/正则、程序化滚动。

与 UI 解耦：组件只调用这里的函数并传入 state。所有 SDK/系统同步调用经
asyncio.to_thread 放入线程池，Flet 事件循环零阻塞。

竞态模型：每次新查询 state.seq+1，在途查询落地前逐段比对 seq，过期结果静默丢弃，
绝不落地 UI；结果分片落地并在批间让出事件循环，保证打字/滚轮优先。
"""

from __future__ import annotations

import asyncio
import time

from csearch import history
from csearch.constants import (
    CHUNK_RENDER_GAP,
    DEBOUNCE_MS,
    MAX_LOADED,
    PAGE_SIZE,
    RESULT_CHUNK,
    ROW_HEIGHT,
    DialogKind,
    Focus,
)
from csearch.controller.common import focus_list, snack
from csearch.engine import EngineUnavailableError, SearchTimeoutError
from csearch.state import AppState, services

# 单会话任务句柄 / 输入时间戳（应用为单窗口，模块级即可）
_debounce_task: asyncio.Task | None = None
_refresh_task: asyncio.Task | None = None
_last_input_ts = 0.0


def cancel_pending_debounce() -> None:
    """取消仍在防抖窗口内的搜索任务（回车 / 切换正则时调用，避免竞争）。"""
    global _debounce_task
    if _debounce_task is not None:
        _debounce_task.cancel()
        _debounce_task = None


# --------------------------------------------------------------------- 输入 / 防抖
def on_query_changed(state: AppState, value: str) -> None:
    global _last_input_ts
    if value == state.query:
        return  # IME 组合等重复事件：跳过，避免无效搜索与多余重建
    state.query = value
    # 结果列表激活时吞掉原生滚轮（由滚轮桥统一驱动）；书签面板等场景恢复透传
    if services.wheel is not None:
        services.wheel.swallow = bool(value.strip())
    _last_input_ts = time.monotonic()
    # 输入即作废所有在途搜索：过期结果静默丢弃，打字不被结果更新打断
    state.seq += 1
    cancel_pending_debounce()
    if not value.strip():
        # 搜索框无内容：清空结果（结果区展示书签）
        state.searching, state.results, state.total = False, [], 0
        state.selected = set()
        state.last_query = ""
        services.wheel_acc, state.max_ext = 0.0, 0.0
        return
    _debounce_task = asyncio.create_task(_debounced(state))


async def _debounced(state: AppState) -> None:
    try:
        await asyncio.sleep(DEBOUNCE_MS / 1000)
    except asyncio.CancelledError:
        return  # 防抖窗口内又有新输入：放弃本次
    try:
        # shield：进入搜索后即使任务被取消也让其在后台跑完，由内部 seq 守卫决定
        # 是否落地，避免取消导致 searching 卡死
        await asyncio.shield(run_search(state))
    except asyncio.CancelledError:
        pass


def set_query(state: AppState, text: str, *, run: bool = True) -> None:
    """程序化写入搜索框文本（清空 / 应用书签 / 启动回填的唯一入口）。

    必须走 ``query_set_seq``：搜索框控件被 ``SearchBar`` 用 use_memo 长期持有
    （为的是让打字期间零属性下发、不打断 IME 组合），因此只有依赖变化才会重建
    并把新文本下发到客户端。用户输入不走这里，走 ``on_query_changed``。
    """
    state.query = text
    state.query_set = text
    state.query_set_seq += 1
    if services.wheel is not None:
        services.wheel.swallow = bool(text.strip())
    global _last_input_ts
    _last_input_ts = time.monotonic()
    state.seq += 1  # 作废在途搜索
    cancel_pending_debounce()
    if not text.strip():
        # 搜索框无内容：清空结果（结果区展示书签）
        state.searching, state.results, state.total = False, [], 0
        state.selected = set()
        state.last_query = ""
        services.wheel_acc, state.max_ext = 0.0, 0.0
        return
    if run:
        asyncio.create_task(run_search(state))


# --------------------------------------------------------------------- 搜索主流程
async def run_search(state: AppState, *, keep_selection: bool = False) -> None:
    if not state.engine_ok:
        ok, msg, db = await asyncio.to_thread(services.engine.check_status)
        state.engine_ok, state.engine_msg, state.index_ready = ok, msg, db
        if not ok:
            state.searching = False
            snack(msg)
            return
    query = services.engine.build_query(
        state.query, state.category, state.time_range, state.size_range, state.use_regex
    )
    if not query.strip():
        state.searching, state.results, state.total = False, [], 0
        state.last_query = ""
        return

    seq = state.seq + 1
    state.seq, state.searching = seq, True
    sort_val = services.engine.sort_value(state.sort_col, state.sort_desc)
    t0 = time.perf_counter()
    try:
        outcome = await asyncio.to_thread(
            services.engine.search, query, sort_val, 0, PAGE_SIZE
        )
    except EngineUnavailableError as e:
        if state.seq == seq:  # 只处理最新一次搜索的错误
            state.engine_ok, state.engine_msg = False, str(e)
            state.searching, state.results, state.total = False, [], 0
            snack(str(e))
        return
    except SearchTimeoutError as e:
        if state.seq == seq:
            state.searching, state.results, state.total = False, [], 0
            snack(str(e))
        return
    except Exception as e:  # noqa: BLE001
        if state.seq == seq:
            state.searching = False
            snack(f"搜索出错：{e}")
        return
    if state.seq != seq:
        return  # 输入已变化：过期结果静默丢弃

    counts = await asyncio.to_thread(
        history.get_counts, (r.full_path for r in outcome.rows)
    )
    if state.seq != seq:
        return  # 取运行次数期间输入又变化：同样丢弃
    for row in outcome.rows:
        row.run_count = counts.get(row.full_path, 0)

    # 先更新轻量状态（总数/耗时/搜索中立即刷新），再分片落地结果。
    # 一次性渲染 200 行的同步渲染会阻塞事件循环 50~200ms；分片 + 批间让出，
    # 结果渐进可见，键盘/滚轮事件在批次间优先处理。
    prev = set(state.selected)
    rows = outcome.rows
    state.total = outcome.total
    state.elapsed_ms = (time.perf_counter() - t0) * 1000
    state.searching = False
    state.last_query, state.last_sort = query, sort_val
    services.wheel_acc, state.max_ext = 0.0, 0.0  # 新结果集回到顶部

    for i in range(0, len(rows), RESULT_CHUNK):
        if state.seq != seq:
            return  # 输入已变化：停止填充，由新搜索接手
        state.results = rows[: i + RESULT_CHUNK]
        # 给 flet 调度器实际运行窗口完成本片渲染（sleep(0) 不够）
        await asyncio.sleep(CHUNK_RENDER_GAP)
    if state.seq != seq:
        return
    state.selected = {i for i in prev if i < len(rows)} if keep_selection else set()
    state.anchor = state.anchor if keep_selection else -1


# --------------------------------------------------------------------- 增量加载
def no_more_to_load(state: AppState) -> bool:
    """底部是否已无更多可加载（硬边界，用于抑制越界弹动）。"""
    if state.searching or state.loading_more or not state.last_query:
        return False
    loaded = len(state.results)
    return loaded >= state.total or loaded >= MAX_LOADED


async def load_more(state: AppState) -> None:
    if state.searching or not state.last_query or state.loading_more:
        return
    loaded = len(state.results)
    if loaded >= state.total or loaded >= MAX_LOADED:
        return
    state.loading_more = True
    seq = state.seq
    try:
        outcome = await asyncio.to_thread(
            services.engine.search, state.last_query, state.last_sort, loaded, PAGE_SIZE
        )
        if state.seq != seq:
            return  # 期间查询已变化：丢弃过期分页
        # 分片追加，批间让出事件循环
        for i in range(0, len(outcome.rows), RESULT_CHUNK):
            if state.seq != seq:
                return
            state.results = state.results + outcome.rows[: i + RESULT_CHUNK]
            await asyncio.sleep(CHUNK_RENDER_GAP)
    except Exception:  # noqa: BLE001
        pass
    finally:
        state.loading_more = False


# --------------------------------------------------------------------- 静默刷新
async def silent_refresh(state: AppState) -> None:
    """索引变更静默刷新（去抖，保留选中）。"""
    global _refresh_task
    if _refresh_task is not None:
        _refresh_task.cancel()
    _refresh_task = asyncio.create_task(_do_refresh(state))


async def _do_refresh(state: AppState) -> None:
    await asyncio.sleep(0.8)
    # 用户正在输入（最近 0.5s 内有按键）时跳过，避免半截结果打断打字
    if time.monotonic() - _last_input_ts < 0.5:
        return
    if not state.searching:
        await run_search(state, keep_selection=True)


# --------------------------------------------------------------------- 排序 / 过滤 / 正则
def on_sort(state: AppState, column: str) -> None:
    if column == "run_count":
        return  # 运行次数为本地数据，不参与 Everything 服务端排序
    if state.sort_col == column:
        state.sort_desc = not state.sort_desc
    else:
        state.sort_col, state.sort_desc = column, False
    asyncio.create_task(run_search(state))


def on_filter(state: AppState, field_name: str, value: str) -> None:
    match field_name:
        case "category":
            state.category = value
        case "time":
            state.time_range = value
        case "size":
            if value == "custom":
                state.size_min, state.size_max = "", ""
                state.dialog = DialogKind.SIZE
                return
            state.size_range = value
        case _:
            return
    if state.query.strip():
        asyncio.create_task(run_search(state))


def toggle_regex(state: AppState) -> None:
    """切换正则搜索并立即按新模式重查（先取消防抖旧任务，避免刷新竞争/闪烁）。"""
    state.use_regex = not state.use_regex
    cancel_pending_debounce()
    if state.query.strip():
        asyncio.create_task(run_search(state))


# --------------------------------------------------------------------- 程序化滚动
async def scroll_results(
    state: AppState, delta: int | None = None, *, row: int | None = None
) -> None:
    """结果列表滚动：delta=相对像素；row=滚动到指定行（键盘导航跟随）。

    统一走 ListView.scroll_to() 绝对偏移（本地累计 wheel_acc，由 on_scroll 同步
    真实位置），避免部分客户端 delta 滚动与原生滚轮互相抵消。
    """
    if not state.results:
        return
    list_view = services.results_list
    if list_view is None or list_view.current is None:
        return
    try:
        if row is not None:
            # 固定行高：把选中行滚到视口中部附近，并夹紧到最大范围避免越界回弹
            offset = max(0, row * ROW_HEIGHT - 90)
            if state.max_ext > 0:
                offset = min(offset, state.max_ext)
            await list_view.current.scroll_to(offset=offset)
        elif delta:
            acc = max(0.0, services.wheel_acc + delta)  # 负 offset 会被解释为距末尾
            if state.max_ext > 0:
                acc = min(acc, state.max_ext)
            services.wheel_acc = acc
            await list_view.current.scroll_to(offset=acc)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------- 回车两步走
async def submit(state: AppState) -> None:
    """搜索框回车：第一次选中「运行次数最大」的结果（无记录则第一个），
    再次回车打开；若已有选中（鼠标点击等）则直接打开。"""
    if not state.query.strip():
        return
    # 取消防抖中的旧任务，避免其与回车搜索竞争导致结果被 seq 守卫丢弃
    cancel_pending_debounce()
    current = services.engine.build_query(
        state.query, state.category, state.time_range,
        state.size_range, state.use_regex,
    )
    if state.searching or not state.results or state.last_query != current:
        await run_search(state)
    if not state.results:
        return
    if state.focus == Focus.LIST:
        return  # 列表焦点下回车由页面级键盘事件处理，避免重复打开
    if not state.selected:
        from csearch.controller.selection import best_result_index

        best = best_result_index(state)
        state.selected, state.anchor = {best}, best
        focus_list(state)
        asyncio.create_task(scroll_results(state, None, row=best))
        return
    from csearch.controller.actions import open_selected

    await open_selected(state)
