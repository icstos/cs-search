"""结果列表滚动适配器：把 ``ListView`` 收敛为 ``ScrollTarget`` 端口。

viewmodel 只调用 ``await scroll_to(offset)``，不接触任何控件对象。
"""

from __future__ import annotations

import ui

#: 结果列表控件引用（viewmodel 程序化滚动经 ListViewScroller 使用）
results_list_ref = ui.Ref[ui.ListView]()


class ListViewScroller:
    """``ScrollTarget`` 端口的 Flet 实现（惰性读取 Ref.current）。"""

    def __init__(self, ref: ui.Ref[ui.ListView]) -> None:
        self._ref = ref

    async def scroll_to(self, offset: float) -> None:
        view = self._ref.current
        if view is None:
            return
        await view.scroll_to(offset=offset)
