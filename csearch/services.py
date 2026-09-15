"""跨线程事件桥：托盘 / 热键 / 滚轮 / 索引线程 → asyncio 主循环。

后台守护线程调用 emit() 非阻塞入队；主事件循环在 bridge_loop 中 await next()
取事件并执行 GUI 操作，从而保证所有 Flet 控件操作都在主线程完成。
"""

from __future__ import annotations

import asyncio
import queue
from typing import Any

# 事件结构：{"type": 事件名, 其余为负载字段}
type BridgeEvent = dict[str, Any]


class EventBridge:
    """线程安全事件桥（queue.Queue 自身线程安全）。"""

    def __init__(self) -> None:
        self._queue: queue.Queue[BridgeEvent] = queue.Queue()

    def emit(self, event: str, **payload: Any) -> None:
        try:
            self._queue.put_nowait({"type": event, **payload})
        except Exception:  # noqa: BLE001
            pass

    async def next(self, timeout: float = 0.3) -> BridgeEvent | None:
        try:
            return await asyncio.to_thread(self._queue.get, True, timeout)
        except queue.Empty:
            return None
