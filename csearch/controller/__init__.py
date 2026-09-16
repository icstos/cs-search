"""业务控制器门面：UI 层统一 ``from csearch import controller`` 后按域调用。

子模块按职责拆分，依赖方向单向向下（无环）：
    common → search → selection/actions/bookmarks/settings/columns/window
           → menu → keyboard → session
本文件仅做 re-export，不含逻辑。
"""

from csearch.controller.actions import (
    confirm_run_count,
    copy_names,
    copy_paths,
    delete_selected,
    launch_everything,
    open_folder,
    open_selected,
    request_run_count,
    reveal_selected,
)
from csearch.controller.bookmarks import (
    apply_bookmark,
    confirm_bookmark,
    confirm_rename,
    delete_bookmark,
    open_bookmark,
    rename_bookmark,
)
from csearch.controller.columns import (
    adapt_columns,
    end_col_drag_gesture,
    start_col_drag,
    start_col_drag_gesture,
    update_col_drag_gesture,
)
from csearch.controller.common import (
    focus_list,
    focus_search,
    page,
    selected_items,
    snack,
)
from csearch.controller.keyboard import on_keyboard
from csearch.controller.menu import (
    close_menu,
    open_bookmark_menu,
    open_row_menu,
)
from csearch.controller.search import (
    cancel_pending_debounce,
    load_more,
    no_more_to_load,
    on_filter,
    on_query_changed,
    on_sort,
    run_search,
    scroll_results,
    silent_refresh,
    submit,
    toggle_regex,
)
from csearch.controller.selection import (
    best_result_index,
    ensure_selected,
    move_selection,
    on_row_click,
)
from csearch.controller.session import bridge_loop, init_app
from csearch.controller.settings import confirm_hotkey, confirm_size, open_hotkey
from csearch.controller.window import (
    hide_to_tray,
    on_window_event,
    quit_app,
    show_window,
    toggle_window,
)

__all__ = [
    "adapt_columns",
    "apply_bookmark",
    "best_result_index",
    "bridge_loop",
    "cancel_pending_debounce",
    "close_menu",
    "confirm_bookmark",
    "confirm_hotkey",
    "confirm_rename",
    "confirm_run_count",
    "confirm_size",
    "copy_names",
    "copy_paths",
    "delete_bookmark",
    "delete_selected",
    "end_col_drag_gesture",
    "ensure_selected",
    "focus_list",
    "focus_search",
    "hide_to_tray",
    "init_app",
    "launch_everything",
    "load_more",
    "move_selection",
    "no_more_to_load",
    "on_filter",
    "on_keyboard",
    "on_query_changed",
    "on_row_click",
    "on_sort",
    "on_window_event",
    "open_bookmark",
    "open_bookmark_menu",
    "open_folder",
    "open_hotkey",
    "open_row_menu",
    "open_selected",
    "page",
    "quit_app",
    "rename_bookmark",
    "request_run_count",
    "reveal_selected",
    "run_search",
    "scroll_results",
    "selected_items",
    "show_window",
    "silent_refresh",
    "snack",
    "start_col_drag",
    "start_col_drag_gesture",
    "submit",
    "toggle_regex",
    "toggle_window",
    "update_col_drag_gesture",
]
