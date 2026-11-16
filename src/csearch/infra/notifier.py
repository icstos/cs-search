"""ui 轻提示适配器：把 ``Notifier`` 端口落到 cs-ui 的 ``Message`` 上。

放在 infra 的原因与 ``UiWindowAdapter`` 一致：它是「与 UI 技术栈交互」的实现细节，
viewmodel 只表达「要提示什么」，不关心用哪种控件呈现。

为什么用 ``Message``（而不是 ``Notification`` 或裸 ``SnackBar``）：
- cs-ui 0.2 把原来的 ``Toast`` 拆成了两支 —— ``Message`` 是「我做了什么」的回执
  （短、居中、几秒即走），``Notification`` 是「系统发生了什么」的通报（带标题、
  贴角、可常驻）。本应用的提示全部是前者，用 ``Notification`` 会像报警。
- 裸 ``SnackBar`` 走弹层栈、一次只能一条、位置钉在底部，会盖住状态栏。
"""

from __future__ import annotations

import ui


class UiNotifier:
    """``Notifier`` 端口的 cs-ui 实现。"""

    def __init__(self, page: ui.Page) -> None:
        self._page = page

    def notify(self, message: str) -> None:
        """弹出一条轻提示；任何异常都吞掉，绝不影响主流程。

        ``grouping=True`` 让内容相同、时间相近的提示合并成「已复制 ×3」并重置
        倒计时 —— 连点几次操作不该在屏幕上刷出一串同样的条。
        """
        try:
            ui.Message.info(
                message,
                page=self._page,
                duration=2200,
                grouping=True,
            )
        except Exception:  # noqa: BLE001
            pass
