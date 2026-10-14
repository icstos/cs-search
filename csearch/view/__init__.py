"""视图层：纯 Flet 组件渲染与事件分发，无任何业务逻辑。

- 渲染：所有界面由 ``ctx.state`` 派生（UI = f(状态)）；
- 交互：只调用 ``ctx.<viewmodel>.<方法>``；
- 不 import 任何 ``service`` / ``infra`` 具体实现（只依赖 ``viewmodel`` 与 ``models``）。
"""

from csearch.view.app import App
from csearch.view.bookmarks import BookmarksPanel
from csearch.view.menu import menu_layer
from csearch.view.results import Results
from csearch.view.searchbar import SearchBar
from csearch.view.statusbar import StatusBar

__all__ = [
    "App",
    "BookmarksPanel",
    "Results",
    "SearchBar",
    "StatusBar",
    "menu_layer",
]
