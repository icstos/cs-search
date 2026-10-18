"""搜索视图模型：防抖输入、分页查询、增量加载、外部变更同步、排序/过滤/正则、程序化滚动。

与 UI 解耦：view 只调用本层方法。所有 SDK / 系统同步调用经 service 层的线程池执行，
Flet 事件循环零阻塞。

竞态模型：每次新查询 ``state.seq + 1``，在途查询落地前逐段比对 seq，过期结果静默丢弃，
绝不落地 UI；结果分片落地并在批间让出事件循环，保证打字/滚轮优先。

外部变更同步（``sync_loop``）：Everything 索引会跟着文件系统变，但结果列表不会自己刷新。
当前 SDK DLL 没有变更通知 API，只能轮询，故按「浅探 / 全探」两级探针把延迟压到亚秒级、
开销压在 ~1% 单核；确认变化后由 ``_apply_changes`` 原地补丁式落地（复用行对象、按路径
迁移选中、不重置滚动），绝不是重跑一次搜索。
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
    SYNC_DEEP_EVERY,
    SYNC_QUIET_MS,
    SYNC_TICK_MS,
)
from csearch.models.entities import ResultItem, SearchOutcome
from csearch.models.enums import DialogKind, Focus
from csearch.models.errors import EngineUnavailableError, SearchTimeoutError

if TYPE_CHECKING:
    from csearch.viewmodel.context import AppContext


def _row_key(row: ResultItem) -> tuple:
    """行的「可见身份」：覆盖全部参与渲染的输入（名称/图标由 full_path、is_folder 派生，
    体积/时间文案由 size、mtime 派生，次数列由 run_count 派生）。"""
    return (row.full_path, row.mtime, row.size, row.is_folder, row.run_count)


class SearchViewModel:
    """搜索流程编排（防抖 → 分页 → 分片落地 → 增量加载 → 外部变更同步）。"""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._s = ctx.services
        self.state = ctx.state
        # 单会话任务句柄 / 输入时间戳（应用为单窗口，实例级即可）
        self._debounce_task: asyncio.Task[None] | None = None
        self._last_input_ts = 0.0
        # 浅探基准：total + 首行身份 / 已加载区间末行身份（两者一起判，见 _shallow_changed）
        self._probe_key: tuple | None = None
        self._tail_key: tuple | None = None

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
        self._probe_key = None
        self._tail_key = None

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

        # 保留选中：以「完整路径」而非行号迁移 —— 重查期间结果集可能因外部增删而整体
        # 位移，按行号迁移会把选中落到另一个文件上。
        prev = {
            self.state.results[i].full_path
            for i in self.state.selected
            if i < len(self.state.results)
        }
        prev_anchor = (
            self.state.results[self.state.anchor].full_path
            if 0 <= self.state.anchor < len(self.state.results)
            else None
        )
        rows = outcome.rows
        self.state.total = outcome.total
        self.state.elapsed_ms = (time.perf_counter() - t0) * 1000
        self.state.searching = False
        self.state.last_query, self.state.last_sort = query, sort_val
        self._s.wheel_acc = 0.0
        self.state.max_ext = 0.0  # 新结果集回到顶部
        # 同步探针基准对齐本次结果（否则下一拍会拿旧查询的基准比出新差异）
        self._remember(rows, outcome.total)

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
        if keep_selection:
            self.state.selected = {
                i for i, r in enumerate(rows) if r.full_path in prev
            }
            self.state.anchor = next(
                (i for i, r in enumerate(rows) if r.full_path == prev_anchor), -1
            )
        else:
            self.state.selected, self.state.anchor = set(), -1

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

    # ------------------------------------------------------------------ 外部变更同步
    # 目标：外部程序（资源管理器、其它工具）增删改文件后，列表**立刻**跟着变，
    # 且不打断用户（不塌回一页、不跳回顶部、不重建全部行）。
    #
    # 为什么是轮询（改前先读）：everytools 附带的 Everything64.dll 是 1.4 SDK，实测
    # 其 90 个导出符号里没有任何变更通知 API（SetReplyWindow 只是「异步查询完成」的
    # 回执窗口，不是索引变更推送），everythingtools 也没暴露 1.5 客户端的事件订阅。
    # 于是唯一可行路径是轮询，工程重点变成「把延迟压到亚秒、把开销压到可忽略」：
    #
    #   浅探（每拍，2 × max=1）：total + 首行 + 末行身份 → 覆盖新建/删除/移入移出/改名位移
    #   全探（每 N 拍或浅探有变化，max=已加载行数）→ 兜底覆盖区间内的任意细微变化
    #
    # 实测（278 万条目索引）：max=1 约 3~5ms、max=200 约 10~36ms，开销几乎全在
    # Everything 侧的搜索+排序，与 max 弱相关。故浅探很便宜，可高频跑。
    async def sync_loop(self) -> None:
        """外部文件变更的实时同步循环（窗口不可见时完全不探，让出 CPU）。

        以「视图可见性」作为开关：隐藏到托盘时用户根本看不到结果，探了纯属白烧 CPU；
        托盘唤回（或取消最小化）后的第一拍直接做全探，把隐藏期间的变更一次性补上。
        """
        tick = 0
        was_visible = False
        while True:
            await asyncio.sleep(SYNC_TICK_MS / 1000)
            if self.state.quitting:
                return
            if not self._s.window.is_visible():
                was_visible, tick = False, 0
                continue
            deep = (not was_visible) or tick % SYNC_DEEP_EVERY == 0
            was_visible, tick = True, tick + 1
            if not self._sync_ready():
                continue
            try:
                await self._probe_changes(deep=deep)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                continue  # 探针失败（引擎断开/超时）不该打扰用户，等下一拍

    def _sync_ready(self) -> bool:
        """本拍能否探测：引擎可用、无在途查询、用户不在打字、确实有结果集在展示。"""
        if not self.state.engine_ok or self.state.searching or self.state.loading_more:
            return False  # 在途查询会占住 DLL 锁，插队只会两边都慢
        if not self.state.query.strip() or not self.state.last_query:
            return False  # 空查询展示书签面板，无结果可同步
        return time.monotonic() - self._last_input_ts >= SYNC_QUIET_MS / 1000

    @staticmethod
    def _probe_of(rows: list[ResultItem], total: int) -> tuple:
        """浅探基准之一：总数 + 首行身份。"""
        return (total, *(_row_key(r) for r in rows[:1]))

    @staticmethod
    def _tail_of(rows: list[ResultItem]) -> tuple | None:
        """浅探基准之二：已加载区间的**末行**身份（空结果集为 None）。"""
        return _row_key(rows[-1]) if rows else None

    def _remember(self, rows: list[ResultItem], total: int) -> None:
        """把探针基准对齐到「刚落地的那批结果」，下一次探测以它为参照。"""
        self._probe_key = self._probe_of(rows, total)
        self._tail_key = self._tail_of(rows)

    async def _shallow_changed(
        self, query: str, sort_val: int, seq: int
    ) -> bool | None:
        """浅探是否有变化：True 有 / False 无 / None 探测已过期（期间用户重新搜索）。

        为什么除首行外还要再采一次**末行**（改前先读）：改名既不改总数、又常常不改
        首行（"bbb.txt" 改名成 "zzz.txt"，首行仍然是 "aaa.txt"），只靠首行完全看不见
        它，只能等每 N 拍一次的全探兜底 —— 真机实测这种改名的落地延迟是 1.95s，而新建
        /删除只要 0.4~0.9s。补一次末行采样（offset=已加载行数-1, max=1）之后，任何
        让已加载区间内行序发生位移的变更都会在**下一拍（≤0.7s）**被抓到；
        代价是多一次 max=1 查询（实测 3~5ms，约 1% 单核）。
        """
        head = await self._s.search.search_page(query, sort_val, 0, 1)
        if self.state.seq != seq:
            return None
        if (
            self._probe_key is not None
            and self._probe_of(head.rows, head.total) != self._probe_key
        ):
            return True
        loaded = len(self.state.results)
        if loaded < 2 or self._tail_key is None:
            return False  # 只有 0/1 行时首行即末行，上面那次查询已经覆盖
        tail = await self._s.search.search_page(query, sort_val, loaded - 1, 1)
        if self.state.seq != seq:
            return None
        return not tail.rows or _row_key(tail.rows[0]) != self._tail_key

    async def _probe_changes(self, *, deep: bool) -> None:
        """浅探 → 必要时升格全探 → 确认有变化才落地。

        ``deep`` 为 True 时**跳过浅探**（全探本身就能得出同一结论）。
        查询次数：浅拍 2 次 max=1（约 8ms），深拍 1 次 max=已加载行数（约 16ms）。
        """
        query, sort_val = self.state.last_query, self.state.last_sort
        seq = self.state.seq
        if not deep:
            changed = await self._shallow_changed(query, sort_val, seq)
            if changed is None or not changed:
                return
        # 全探范围 = 已加载行数（用户看得到的都在里面），至少一页
        count = min(max(len(self.state.results), PAGE_SIZE), MAX_LOADED)
        outcome = await self._s.search.search_page(query, sort_val, 0, count)
        if self.state.seq != seq:
            return
        self._apply_changes(self.state.results, outcome)
        self._remember(outcome.rows, outcome.total)


    async def sync_refresh(self) -> None:
        """立即原地同步一次（本程序自己删文件后补偿，或需要主动对齐时调用）。"""
        if not self._sync_ready():
            return
        seq = self.state.seq
        count = min(max(len(self.state.results), PAGE_SIZE), MAX_LOADED)
        try:
            outcome = await self._s.search.search_page(
                self.state.last_query, self.state.last_sort, 0, count
            )
        except Exception:  # noqa: BLE001
            return
        if self.state.seq != seq:
            return
        self._apply_changes(self.state.results, outcome)
        self._remember(outcome.rows, outcome.total)

    def _apply_changes(
        self, old: list[ResultItem], outcome: SearchOutcome
    ) -> None:
        """把外部变更**原地**落到状态上（这是「实时且不打扰」的关键，改前先读）。

        为什么不能直接调 ``run_search``：那会把已加载的多页结果塌回一页、把列表滚回
        顶部（``max_ext = 0``）、并重建全部行控件（实测约 0.9ms/行，200 行 ≈ 180ms）。
        外部变化是「随时发生、用户没有主动动作」，必须是补丁而不是重来：

        - 内容一致的行**复用同一个 ResultItem 对象**——行控件缓存的键含 ``id(item)``
          与行号，复用对象才能让「只有少数行变了」的更新近乎零重绘；
        - 只有 ``total`` 变了（增删发生在已加载区间之外）时**完全不碰 results**，
          状态栏自己会更新，列表零开销；
        - 选中与锚点按**完整路径**迁移：插入/删除会让行号整体偏移，按行号迁移会把
          选中落到别的文件上（外部删掉的选中项则自然从集合里消失）；
        - 不触碰 ``max_ext`` / ``wheel_acc``：列表滚动位置保持不动。
        """
        merged: list[ResultItem] = []
        rows_changed = len(outcome.rows) != len(old)
        for i, row in enumerate(outcome.rows):
            prev = old[i] if i < len(old) else None
            if prev is not None and _row_key(prev) == _row_key(row):
                merged.append(prev)  # 同位置同内容：复用对象，该行控件零重建
            else:
                merged.append(row)
                rows_changed = True

        total_changed = outcome.total != self.state.total

        if rows_changed:
            selected = {
                old[i].full_path for i in self.state.selected if i < len(old)
            }
            anchor = (
                old[self.state.anchor].full_path
                if 0 <= self.state.anchor < len(old)
                else None
            )
            # 先算好再整体赋值：中间态不对外可见，避免渲染到「新结果 + 旧选中」
            new_selected = {
                i for i, r in enumerate(merged) if r.full_path in selected
            }
            new_anchor = next(
                (i for i, r in enumerate(merged) if r.full_path == anchor), -1
            )
            self.state.results = merged
            self.state.selected = new_selected
            self.state.anchor = new_anchor
        if total_changed:
            self.state.total = outcome.total

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
