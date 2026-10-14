"""设置视图模型：全局热键、自定义大小区间。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from csearch.models.constants import is_valid_hotkey
from csearch.models.enums import DialogKind

if TYPE_CHECKING:
    from csearch.viewmodel.context import AppContext


class SettingsViewModel:
    """设置类对话框的交互逻辑。"""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._s = ctx.services
        self.state = ctx.state

    # ------------------------------------------------------------------ 全局热键
    def open_hotkey(self) -> None:
        self.state.hotkey_text = self._s.config.load().hotkey
        self.state.dialog = DialogKind.HOTKEY

    def confirm_hotkey(self) -> None:
        combo = self.state.hotkey_text.strip().lower()
        if combo and not is_valid_hotkey(combo):
            # 纯修饰键（alt / ctrl+alt）或残缺组合（alt+）：注册后会变成「按修饰键即
            # 唤起」，这里先挡下并给出可操作的提示，对话框保持打开
            self._s.toast("热键需包含至少一个非修饰键，如 alt+space、ctrl+shift+f")
            return
        if combo:
            if not self._s.session.set_hotkey(combo):
                self._s.toast("热键注册失败，请更换组合（如 alt+space / ctrl+shift+f）")
                return
        else:
            self._s.session.set_hotkey("")  # 空 = 禁用
        self._s.config.save_hotkey(combo)
        self.state.dialog = None
        self._s.toast(f"全局热键已更新：{combo or '（已禁用）'}")

    # ------------------------------------------------------------------ 自定义大小
    def confirm_size(self) -> None:
        """确认自定义大小区间（输入单位 MB，转换为字节）。"""

        def to_bytes(text: str) -> int | None:
            text = text.strip()
            if not text:
                return None
            try:
                value = float(text)
                return int(value * 1024 * 1024) if value >= 0 else None
            except ValueError:
                return None

        lo, hi = to_bytes(self.state.size_min), to_bytes(self.state.size_max)
        if lo is None and hi is None:
            self.state.dialog = None
            return
        if lo is not None and hi is not None and lo > hi:
            self._s.toast("最小不能大于最大")
            return
        self.state.size_range = f"custom:{lo or ''},{hi or ''}"
        self.state.dialog = None
        asyncio.create_task(self._ctx.search.run_search())
