"""跨线程事件桥：托盘 / 热键 / 滚轮 / 索引线程 → asyncio 主循环。

后台守护线程调用 emit() 非阻塞投递；主事件循环在 next() 中 await 取事件并执行
GUI 操作，从而保证所有 Flet 控件操作都在主线程完成。

实现要点（改前先读）：
- 用 ``asyncio.Queue`` + ``loop.call_soon_threadsafe`` 取代「线程池里阻塞轮询」：
  轮询在空闲时每 0.3s 就要唤醒一次线程池与事件循环，纯属白烧 CPU。现在 next()
  是真正的事件驱动等待，空闲时零唤醒。
- 事件循环尚未绑定（桥已建、消费循环未启动）时，emit 先落到 _pending 暂存，
  由首次 next() 一次性搬进队列，保证不丢事件。
"""

from __future__ import annotations

import asyncio
import threading
from collections import deque

from csearch.models.entities import BridgeEvent


class AsyncioEventBus:
    """线程安全事件桥（emit 可在任意线程调用，next 只能在事件循环线程 await）。"""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[BridgeEvent] = asyncio.Queue()
        self._pending: deque[BridgeEvent] = deque()
        self._lock = threading.Lock()

    def emit(self, event: str, **payload: object) -> None:
        """非阻塞投递事件（可从任意线程调用）。"""
        item: BridgeEvent = {"type": event, **payload}
        loop = self._loop
        if loop is not None:
            try:
                loop.call_soon_threadsafe(self._queue.put_nowait, item)
                return
            except RuntimeError:
                pass  # 循环已关闭：降级为暂存，避免抛到托盘/热键线程
        with self._lock:
            self._pending.append(item)

    async def next(self) -> BridgeEvent:
        """等待下一个事件（事件驱动，无超时轮询）。"""
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
            with self._lock:
                buffered, self._pending = list(self._pending), deque()
            for item in buffered:
                self._queue.put_nowait(item)
        return await self._queue.get()
