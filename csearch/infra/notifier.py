"""ui 轻提示适配器：把 ``Notifier`` 端口落到 cs-ui 的 ``Toast`` 上。

放在 infra 的原因与 ``UiWindowAdapter`` 一致：它是「与 UI 技术栈交互」的实现细节，
viewmodel 只表达「要提示什么」，不关心用 Toast 还是别的方式。

为什么用 ``Toast`` 而不是裸 ``SnackBar``：cs-ui 的 Toast 已经带语义色 + 图标 +
浮动边距，与应用其余部分的语义色约定一致；裸 SnackBar 是贴底整条，会盖住状态栏。
"""

from __future__ import annotations

import ui


class UiNotifier:
    """``Notifier`` 端口的 cs-ui 实现。"""

    def __init__(self, page: ui.Page) -> None:
        self._page = page

    def notify(self, message: str) -> None:
        """弹出一条轻提示；任何异常都吞掉，绝不影响主流程。

        显式给宽度：不给宽度时 SnackBar 会铺满整窗底部，把状态栏整条盖住
        （实测「书签已保存」会遮住结果计数与引擎状态）。限宽后是居中的浮动胶囊，
        既保留 cs-ui 的语义配色，也不打断用户对状态栏的读取。
        """
        try:
            ui.Toast(
                content=message,
                style_type=ui.StyleType.INFO,
                duration=2200,
                width=360,
            ).show(page=self._page)
        except Exception:  # noqa: BLE001
            pass
