"""主窗口适配器：把 Flet ``Page.window`` 收敛为领域无关的 ``Window`` 端口。

为什么放在 infra：窗口的显示/隐藏/置前/销毁本质是「与 UI 技术栈的交互」，
把它抽象成端口后，viewmodel 只需调用 ``window.show()`` 之类的语义方法，
既不 import flet，也不接触任何控件对象。

注意（历史坑）：窗口事件挂在 ``Window.on_event``，Page 并没有 ``on_window_event``；
写成 ``page.on_window_event`` 只是个普通属性，flet 永远不读。
"""

from __future__ import annotations

import flet as ft

from csearch.models.entities import WindowGeometry


class FletWindowAdapter:
    """``Window`` 端口的 Flet 实现（构造时注入 Page）。"""

    def __init__(self, page: ft.Page) -> None:
        self._page = page

    @property
    def title(self) -> str:
        return str(self._page.title or "")

    def geometry(self) -> WindowGeometry:
        window = self._page.window
        return WindowGeometry(
            width=int(window.width or 1040),
            height=int(window.height or 680),
            left=int(window.left) if window.left is not None else None,
            top=int(window.top) if window.top is not None else None,
            maximized=bool(window.maximized),
        )

    def logical_width(self) -> float:
        return float(self._page.window.width or 1040)

    def viewport_size(self) -> tuple[float, float]:
        return float(self._page.width or 0.0), float(self._page.height or 0.0)

    def is_visible(self) -> bool:
        return bool(self._page.window.visible)

    def show(self) -> None:
        self._page.window.visible = True
        self._page.window.minimized = False
        self._page.update()

    def hide(self) -> None:
        self._page.window.visible = False
        self._page.update()

    async def to_front(self) -> None:
        await self._page.window.to_front()

    def set_prevent_close(self, value: bool) -> None:
        self._page.window.prevent_close = value

    async def destroy(self) -> None:
        await self._page.window.destroy()
