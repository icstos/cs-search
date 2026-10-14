"""会话视图模型：应用初始化编排与后台事件桥消费循环。

- ``init``：拉起后台服务、探测引擎、加载书签、接线索引监听、启动即搜索；
- ``bridge_loop``：把后台线程事件翻译为对其它 ViewModel 的调用（GUI 全程在主线程）。
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from csearch.models.enums import BridgeEventType

if TYPE_CHECKING:
    from csearch.viewmodel.context import AppContext

#: 启动即搜索：设置该环境变量可在启动时自动执行一次搜索（默认展示书签面板）
INIT_QUERY_ENV = "CSEARCH_QUERY"


class SessionViewModel:
    """应用会话编排（初始化 + 事件桥）。"""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._s = ctx.services
        self.state = ctx.state

    # ------------------------------------------------------------------ 初始化
    async def init(self) -> None:
        """组件挂载后的一次性初始化（幂等性由调用方保证）。"""
        # 延迟校验窗口位置：多显示器布局变化时保存的坐标可能失效
        asyncio.create_task(self._ctx.window.ensure_on_screen_later())

        status = await self._s.session.start_background()
        self.state.engine_ok = status.available
        self.state.engine_msg = status.message
        self.state.index_ready = status.index_ready
        self.state.engine_version = self._s.search.version
        self.state.bookmarks = self._s.bookmarks.load()

        # 优先事件驱动通知；官方 1.5 SDK DLL 缺失时降级为 5s 签名轮询
        self._s.session.start_change_monitor()

        # 启动即搜索（环境变量 CSEARCH_QUERY；默认空 = 展示书签面板）
        init_query = os.environ.get(INIT_QUERY_ENV, "").strip()
        if init_query:
            self._ctx.search.set_query(init_query, run=False)  # 程序化回填搜索框
        await self._ctx.search.run_search()

    # ------------------------------------------------------------------ 事件桥
    async def bridge_loop(self) -> None:
        """后台线程事件 → 主线程 GUI 操作的统一分发循环。"""
        while True:
            event = await self._s.bus.next()
            match event.get("type"):
                case BridgeEventType.TOGGLE:
                    await self._ctx.window.toggle()
                case BridgeEventType.SHOW:
                    await self._ctx.window.show()
                case BridgeEventType.HIDE:
                    self._ctx.window.hide()
                case BridgeEventType.QUIT:
                    await self._ctx.window.quit()
                    return
                case BridgeEventType.WHEEL:
                    await self._ctx.search.scroll_results(int(event.get("delta", 0) or 0))
                case BridgeEventType.INDEX_CHANGED:
                    await self._ctx.search.silent_refresh()
