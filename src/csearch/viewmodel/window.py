"""窗口视图模型：托盘显隐 / 唤回抢焦 / 几何记忆 / 窗口事件分发 / 退出。

窗口与屏幕能力分别经 ``Window`` / ``Screen`` 端口调用，本层不接触任何控件。
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from csearch.models.constants import APP_TITLE, MIN_WINDOW_HEIGHT, MIN_WINDOW_WIDTH
from csearch.models.entities import WindowEventData
from csearch.models.enums import WindowEventKind

if TYPE_CHECKING:
    from csearch.viewmodel.context import AppContext


class WindowViewModel:
    """主窗口生命周期与显隐管理。"""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._s = ctx.services
        self.state = ctx.state
        self._geo_task: asyncio.Task | None = None

    # ------------------------------------------------------------------ 显隐
    async def show(self) -> None:
        """唤回窗口：取消最小化、置顶、纠正屏幕外位置并抢回键盘焦点。"""
        try:
            self._s.window.show()
            self._s.screen.ensure_window_on_screen()  # 多显示器布局变化后坐标可能失效
            await self._s.window.to_front()  # 协程必须 await，否则不置顶
        except Exception:  # noqa: BLE001
            pass
        self._s.screen.force_foreground_by_title(APP_TITLE)  # Windows 前台锁定兜底
        self._ctx.selection.focus_search()
        # 唤回时全选搜索框已有内容（一次性标记，SearchBar 重挂载时下发 selection）
        if self.state.query:
            self._s.select_on_focus = True

    def hide(self) -> None:
        """隐藏到托盘，首次弹一次气泡提示。

        托盘图标与全局热键都不可用时，隐藏窗口 = 应用变成唤不回来的后台进程；
        此时降级为真退出，避免「点 X 后既看不见也关不掉」。
        """
        if not self._s.session.tray_available:
            asyncio.create_task(self.quit())
            return
        try:
            self._s.window.hide()
        except Exception:  # noqa: BLE001
            pass
        if not self.state.balloon_shown:
            self.state.balloon_shown = True
            self._s.session.notify("已最小化到系统托盘，全局热键可再次唤起", APP_TITLE)

    async def toggle(self) -> None:
        if self._s.window.is_visible():
            self.hide()
        else:
            await self.show()

    # ------------------------------------------------------------------ 事件
    def handle(self, event: WindowEventData) -> None:
        """窗口事件：关闭→托盘；显示/恢复→焦点回搜索框；缩放/移动→列适配 + 去抖存几何。"""
        match event.kind:
            case WindowEventKind.CLOSE if not self.state.quitting:
                self.hide()
            case WindowEventKind.SHOW:
                self._ctx.selection.focus_search()
                if self.state.query:  # 与 show() 幂等：保证最后一次重挂载仍带全选
                    self._s.select_on_focus = True
            case WindowEventKind.RESTORE:
                self._ctx.selection.focus_search()  # 任务栏/Alt+Tab 唤回同样抢回焦点
            case WindowEventKind.RESIZED | WindowEventKind.MOVED:
                self._ctx.columns.adapt()
                if self._geo_task is not None:
                    self._geo_task.cancel()
                self._geo_task = asyncio.create_task(self._save_geometry_later())

    async def ensure_on_screen_later(self) -> None:
        """启动延迟兜底：等客户端应用完保存的几何后再校验屏幕内位置。"""
        await asyncio.sleep(0.6)
        self._s.screen.ensure_window_on_screen()

    # ------------------------------------------------------------------ 几何记忆
    def _save_geometry(self) -> None:
        """把当前窗口几何写回配置（夹一道最小尺寸下限）。"""
        try:
            geometry = self._s.config.load().window
            current = self._s.window.geometry()
            geometry.width = max(MIN_WINDOW_WIDTH, current.width)
            geometry.height = max(MIN_WINDOW_HEIGHT, current.height)
            if current.left is not None:
                geometry.left = current.left
            if current.top is not None:
                geometry.top = current.top
            geometry.maximized = current.maximized
            self._s.config.save_window(geometry)
        except Exception:  # noqa: BLE001
            pass

    async def _save_geometry_later(self) -> None:
        await asyncio.sleep(0.6)
        self._save_geometry()

    # ------------------------------------------------------------------ 退出
    async def quit(self) -> None:
        """真正退出：停热键/托盘/滚轮/索引监听，再销毁窗口。"""
        if self.state.quitting:
            return
        self.state.quitting = True
        self._save_geometry()
        self._s.session.stop()
        try:
            self._s.window.set_prevent_close(False)
            await self._s.window.destroy()  # 协程必须 await
        except Exception:  # noqa: BLE001
            os._exit(0)
