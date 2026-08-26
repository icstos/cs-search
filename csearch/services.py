"""后台服务：跨线程事件桥。

说明：
- 旧版 ctypes Shell_NotifyIconW 托盘与 HotkeyManager 已迁移到独立模块
  `csearch/tray_manager.py`（pystray + pynput 实现，跨平台、线程安全），
  本文件仅保留线程安全事件桥，供托盘/热键/索引线程 → asyncio 主循环通信。
"""

from __future__ import annotations

import asyncio
import queue


class EventBridge:
    """线程安全事件桥：托盘/热键/滚轮/索引线程 → asyncio 事件循环。

    用法：
    - 后台线程调用 emit("toggle") 入队（非阻塞）；
    - 主事件循环在 bridge_loop 中 await next() 取事件并执行 GUI 操作，
      从而保证所有 Flet 控件操作都在主线程完成。
    """

    def __init__(self) -> None:
        self._q: queue.Queue[dict] = queue.Queue()

    def emit(self, event: str, **payload) -> None:
        try:
            self._q.put_nowait({"type": event, **payload})
        except Exception:  # noqa: BLE001
            pass

    async def next(self, timeout: float = 0.3) -> dict | None:
        try:
            return await asyncio.to_thread(self._q.get, True, timeout)
        except queue.Empty:
            return None
