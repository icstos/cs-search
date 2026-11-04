"""主题适配器：把「明暗模式」这一语义落到 cs-ui 的主题运行时上。

放在 infra 的理由与窗口/提示适配器一致：主题最终要写 ``Page.theme`` / ``Page.theme_mode``，
那是 UI 技术栈的实现细节；viewmodel 只表达「切到浅色 / 深色」，不接触 Page。

为什么复用 ``ui.apply_theme`` 而不是自己拼 ``ft.Theme``（改前先读）：
cs-ui 的主题构造里已经按**桌面端**调过滚动条（4px、悬停才显形）、关掉了移动端的
路由转场动画、并把弹出菜单调成最低容器层 + 阴影。自己再写一份必然与组件库的
观感脱节，而且这些参数会随库升级而变。
"""

from __future__ import annotations

import ui

from csearch.models.constants import THEME_MODES


class UiTheme:
    """``ThemePort`` 的 cs-ui 实现（构造时注入 Page）。"""

    def __init__(self, page: ui.Page) -> None:
        self._page = page

    def mode(self) -> str:
        """当前实际生效的模式（``system`` 已按系统亮度解析）。"""
        return ui.core.theme.current_mode()

    def apply(self, mode: str) -> None:
        """下发模式并立即刷新页面；任何异常都吞掉，绝不影响主流程。"""
        try:
            state = ui.theme_state()
            state.set_mode(mode if mode in THEME_MODES else "system")
            ui.apply_theme(self._page, state)
            self._page.update()
        except Exception:  # noqa: BLE001
            pass
