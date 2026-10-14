"""Flet 轻提示适配器：把 ``Notifier`` 端口落到 SnackBar 上。

放在 infra 的原因与 ``FletWindowAdapter`` 一致：它是「与 UI 技术栈交互」的实现细节，
viewmodel 只表达「要提示什么」，不关心用 SnackBar 还是别的方式。
"""

from __future__ import annotations

import flet as ft


class FletNotifier:
    """``Notifier`` 端口的 Flet 实现。"""

    def __init__(self, page: ft.Page) -> None:
        self._page = page

    def notify(self, message: str) -> None:
        """弹出一条轻提示；任何异常都吞掉，绝不影响主流程。"""
        try:
            self._page.show_dialog(ft.SnackBar(ft.Text(message, size=13), duration=1800))
        except Exception:  # noqa: BLE001
            pass
