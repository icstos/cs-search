"""搜索视图模型：防抖输入、分页查询、增量加载、静默刷新、排序/过滤/正则、程序化滚动。

与 UI 解耦：view 只调用本层方法。所有 SDK / 系统同步调用经 service 层的线程池执行，
Flet 事件循环零阻塞。

竞态模型：每次新查询 ``state.seq + 1``，在途查询落地前逐段比对 seq，过期结果静默丢弃，
绝不落地 UI；结果分片落地并在批间让出事件循环，保证打字/滚轮优先。
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from csearch.models.constants import (
    CHUNK_RENDER_GAP,
    DEBOUNCE_MS,
    MAX_LOADED,
    PAGE_SIZE,
    RESULT_CHUNK,
    ROW_HEIGHT,
)
from csearch.models.enums import DialogKind, Focus
from csearch.models.errors import EngineUnavailableError, SearchTimeoutError

if TYPE_CHECKING:
    from csearch.viewmodel.context import AppContext


class SearchViewModel:
    """搜索流程编排（防抖 → 分页 → 分片落地 → 增量加载 → 静默刷新）。"""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._s = ctx.services
        self.state = ctx.state
        # 单会话任务句柄 / 输入时间戳（应用为单窗口，实例级即可）
        self._debounce_task: asyncio.Task[None] | None = None
        self._refresh_task: asyncio.Task[None] | None = None
        self._last_input_ts = 0.0

    # ------------------------------------------------------------------ 防抖
    def cancel_pending_debounce(self) -> None:
        """取消仍在防抖窗口内的搜索任务（回车 / 切换正则时调用，避免竞争）。"""
        if self._debounce_task is not None:
            self._debounce_task.cancel()
            self._debounce_task = None

    def on_query_changed(self, value: str) -> None:
        """用户输入（打字）路径：绝不向客户端下发控件属性，只更新状态与调度查询。"""
        if value == self.state.query:
            return  # IME 组合等重复事件：跳过，避免无效搜索与多余重建
        self.state.query = value
        # 结果列表激活时吞掉原生滚轮（由滚轮桥统一驱动）；书签面板等场景恢复透传
        self._s.session.set_wheel_swallow(bool(value.strip()))
        self._last_input_ts = time.monotonic()
        # 输入即作废所有在途搜索：过期结果静默丢弃，打字不被结果更新打断
        self.state.seq += 1
        self.cancel_pending_debounce()
        if not value.strip():
            self._clear_results()  # 搜索框无内容：清空结果（结果区展示书签）
            return
        self._debounce_task = asyncio.create_task(self._debounced())

    async def _debounced(self) -> None:
        try:
            await asyncio.sleep(DEBOUNCE_MS / 1000)
        except asyncio.CancelledError:
            return  # 防抖窗口内又有新输入：放弃本次
        try:
            # shield：进入搜索后即使任务被取消也让其在后台跑完，由内部 seq 守卫决定
            # 是否落地，避免取消导致 searching 卡死
            await asyncio.shield(self.run_search())
        except asyncio.CancelledError:
            pass

    def set_query(self, text: str, *, run: bool = True) -> None:
        """程序化写入搜索框文本（清空 / 应用书签 / 启动回填的唯一入口）。

        必须走 ``query_set_seq``：搜索框控件被 SearchBar 用 use_memo 长期持有
        （为的是让打字期间零属性下发、不打断 IME 组合），因此只有依赖变化才会重建
        并把新文本下发到客户端。用户输入不走这里，走 ``on_query_changed``。
        """
        self.state.query = text
        self.state.query_set = text
        self.state.query_set_seq += 1
        self._s.session.set_wheel_swallow(bool(text.strip()))
        self._last_input_ts = time.monotonic()
        self.state.seq += 1  # 作废在途搜索
        self.cancel_pending_debounce()
        if not text.strip():
            self._clear_results()  # 搜索框无内容：清空结果（结果区展示书签）
            return
        if run:
            asyncio.create_task(self.run_search())

    def _clear_results(self) -> None:
        self.state.searching = False
        self.state.results = []
        self.state.total = 0
        self.state.selected = set()
        self.state.last_query = ""
        self._s.wheel_acc = 0.0
        self.state.max_ext = 0.0

    # ------------------------------------------------------------------ 搜索主流程
    async def run_search(self, *, keep_selection: bool = False) -> None:
        if not self.state.engine_ok:
            status = await self._s.search.check_status()
            self.state.engine_ok = status.available
            self.state.engine_msg = status.message
            self.state.index_ready = status.index_ready
            if not status.available:
                self.state.searching = False
                self._s.toast(status.message)
                return
        query = self._s.search.build_query(
            self.state.query,
            self.state.category,
            self.state.time_range,
            self.state.size_range,
            self.state.use_regex,
        )
        if not query.strip():
            self.state.searching = False
            self.state.results = []
            self.state.total = 0
            self.state.last_query = ""
            return

        seq = self.state.seq + 1
        self.state.seq, self.state.searching = seq, True
        sort_val = self._s.search.sort_value(self.state.sort_col, self.state.sort_desc)
        t0 = time.perf_counter()
        try:
            outcome = await self._s.search.search_page(query, sort_val, 0, PAGE_SIZE)
        except EngineUnavailableError as e:
            if self.state.seq == seq:  # 只处理最新一次搜索的错误
                self.state.engine_ok, self.state.engine_msg = False, str(e)
                self.state.searching = False
                self.state.results = []
                self.state.total = 0
                self._s.toast(str(e))
            return
        except SearchTimeoutError as e:
            if self.state.seq == seq:
                self.state.searching = False
                self.state.results = []
                self.state.total = 0
                self._s.toast(str(e))
            return
        except Exception as e:  # noqa: BLE001
            if self.state.seq == seq:
                self.state.searching = False
                self._s.toast(f"搜索出错：{e}")
            return
        if self.state.seq != seq:
            return  # 输入已变化：过期结果静默丢弃

        prev = set(self.state.selected)
        rows = outcome.rows
        self.state.total = outcome.total
        self.state.elapsed_ms = (time.perf_counter() - t0) * 1000
        self.state.searching = False
        self.state.last_query, self.state.last_sort = query, sort_val
        self._s.wheel_acc = 0.0
        self.state.max_ext = 0.0  # 新结果集回到顶部

        # 空结果集必须显式清空：下面的分片循环在 len(rows) == 0 时一次都不执行，
        # 若不清空 state.results 会保留上一次的结果，界面残留旧行且看不到「无匹配结果」。
        if not rows:
            self.state.results = []

        for i in range(0, len(rows), RESULT_CHUNK):
            if self.state.seq != seq:
                return  # 输入已变化：停止填充，由新搜索接手
            self.state.results = rows[: i + RESULT_CHUNK]
            # 给 flet 调度器实际运行窗口完成本片渲染（sleep(0) 不够）
            await asyncio.sleep(CHUNK_RENDER_GAP)
        if self.state.seq != seq:
            return
        self.state.selected = (
            {i for i in prev if i < len(rows)} if keep_selection else set()
        )
        self.state.anchor = self.state.anchor if keep_selection else -1

    # ------------------------------------------------------------------ 增量加载
    def no_more_to_load(self) -> bool:
        """底部是否已无更多可加载（硬边界，用于抑制越界弹动）。"""
        if self.state.searching or self.state.loading_more or not self.state.last_query:
            return False
        loaded = len(self.state.results)
        return loaded >= self.state.total or loaded >= MAX_LOADED

    async def load_more(self) -> None:
        if self.state.searching or not self.state.last_query or self.state.loading_more:
            return
        loaded = len(self.state.results)
        if loaded >= self.state.total or loaded >= MAX_LOADED:
            return
        self.state.loading_more = True
        seq = self.state.seq
        try:
            outcome = await self._s.search.search_page(
                self.state.last_query, self.state.last_sort, loaded, PAGE_SIZE
            )
            if self.state.seq != seq:
                return  # 期间查询已变化：丢弃过期分页
            # 分片追加，批间让出事件循环
            for i in range(0, len(outcome.rows), RESULT_CHUNK):
                if self.state.seq != seq:
                    return
                self.state.results = self.state.results + outcome.rows[: i + RESULT_CHUNK]
                await asyncio.sleep(CHUNK_RENDER_GAP)
        except Exception:  # noqa: BLE001
            pass
        finally:
            self.state.loading_more = False

    # ------------------------------------------------------------------ 静默刷新
    async def silent_refresh(self) -> None:
        """索引变更静默刷新（去抖，保留选中）。"""
        if self._refresh_task is not None:
            self._refresh_task.cancel()
        self._refresh_task = asyncio.create_task(self._do_refresh())

    async def _do_refresh(self) -> None:
        await asyncio.sleep(0.8)
        # 用户正在输入（最近 0.5s 内有按键）时跳过，避免半截结果打断打字
        if time.monotonic() - self._last_input_ts < 0.5:
            return
        if not self.state.searching:
            await self.run_search(keep_selection=True)

    # ------------------------------------------------------------------ 排序 / 过滤 / 正则
    def on_sort(self, column: str) -> None:
        if column == "run_count":
            return  # 运行次数为本地数据，不参与 Everything 服务端排序
        if self.state.sort_col == column:
            self.state.sort_desc = not self.state.sort_desc
        else:
            self.state.sort_col, self.state.sort_desc = column, False
        asyncio.create_task(self.run_search())

    def on_filter(self, field_name: str, value: str) -> None:
        match field_name:
            case "category":
                self.state.category = value
            case "time":
                self.state.time_range = value
            case "size":
                if value == "custom":
                    self.state.size_min, self.state.size_max = "", ""
                    self.state.dialog = DialogKind.SIZE
                    return
                self.state.size_range = value
            case _:
                return
        if self.state.query.strip():
            asyncio.create_task(self.run_search())

    def toggle_regex(self) -> None:
        """切换正则搜索并立即按新模式重查（先取消防抖旧任务，避免刷新竞争/闪烁）。"""
        self.state.use_regex = not self.state.use_regex
        self.cancel_pending_debounce()
        if self.state.query.strip():
            asyncio.create_task(self.run_search())

    # ------------------------------------------------------------------ 程序化滚动
    async def scroll_results(self, delta: int | None = None, *, row: int | None = None) -> None:
        """结果列表滚动：delta=相对像素；row=滚动到指定行（键盘导航跟随）。

        统一走列表 scroll_to() 绝对偏移（本地累计 wheel_acc，由 on_scroll 同步真实
        位置），避免部分客户端 delta 滚动与原生滚轮互相抵消。
        """
        if not self.state.results:
            return
        target = self._s.scroll
        if target is None:
            return
        try:
            if row is not None:
                # 固定行高：把选中行滚到视口中部附近，并夹紧到最大范围避免越界回弹
                offset = max(0, row * ROW_HEIGHT - 90)
                if self.state.max_ext > 0:
                    offset = min(offset, self.state.max_ext)
                await target.scroll_to(offset)
            elif delta:
                acc = max(0.0, self._s.wheel_acc + delta)  # 负 offset 会被解释为距末尾
                if self.state.max_ext > 0:
                    acc = min(acc, self.state.max_ext)
                self._s.wheel_acc = acc
                await target.scroll_to(acc)
        except Exception:  # noqa: BLE001
            pass

    def on_scroll(self, pixels: float, max_extent: float, viewport: float) -> None:
        """列表滚动回调（view 提取滚轮参数后调用）。"""
        # 持续同步真实滚动位置，滚轮桥据此做绝对偏移
        self._s.wheel_acc = pixels
        self.state.max_ext = max_extent
        # 接近底部自动加载下一页（硬边界处不再触发，避免越界弹动）
        if (
            max_extent > 0
            and not self.no_more_to_load()
            and pixels + viewport >= max_extent - 120
        ):
            asyncio.create_task(self.load_more())

    # ------------------------------------------------------------------ 回车两步走
    async def submit(self) -> None:
        """搜索框回车：第一次选中「运行次数最大」的结果（无记录则第一个），
        再次回车打开；若已有选中（鼠标点击等）则直接打开。"""
        if not self.state.query.strip():
            return
        # 取消防抖中的旧任务，避免其与回车搜索竞争导致结果被 seq 守卫丢弃
        self.cancel_pending_debounce()
        current = self._s.search.build_query(
            self.state.query,
            self.state.category,
            self.state.time_range,
            self.state.size_range,
            self.state.use_regex,
        )
        if self.state.searching or not self.state.results or self.state.last_query != current:
            await self.run_search()
        if not self.state.results:
            return
        if self.state.focus == Focus.LIST:
            return  # 列表焦点下回车由页面级键盘事件处理，避免重复打开
        if not self.state.selected:
            best = self._ctx.selection.best_result_index()
            self.state.selected, self.state.anchor = {best}, best
            self._ctx.selection.focus_list()
            asyncio.create_task(self.scroll_results(row=best))
            return
        await self._ctx.actions.open_selected()
