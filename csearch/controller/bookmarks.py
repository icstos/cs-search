"""书签：保存 / 应用 / 重命名 / 删除（JSON 持久化由 store 负责）。"""

from __future__ import annotations

import asyncio

from csearch import store
from csearch.constants import DialogKind
from csearch.controller.common import snack
from csearch.controller.search import run_search
from csearch.models import Bookmark
from csearch.state import AppState


def open_bookmark(state: AppState) -> None:
    """打开「保存书签」对话框，名称默认取当前关键词。"""
    state.bm_edit_id = None
    state.bm_name = (state.query.strip() or "全部文件")[:40]
    state.dialog = DialogKind.BOOKMARK


def confirm_bookmark(state: AppState) -> None:
    store.add_bookmark(
        state.bookmarks, state.bm_name, state.query,
        state.category, state.time_range, state.size_range,
    )
    state.dialog = None
    snack("书签已保存")


def apply_bookmark(state: AppState, bm: Bookmark) -> None:
    """一键应用书签：回填搜索条件并查询。"""
    state.query, state.category = bm.query, bm.category
    state.time_range, state.size_range = bm.time_range, bm.size_range
    asyncio.create_task(run_search(state))


def rename_bookmark(state: AppState, bm: Bookmark) -> None:
    state.bm_edit_id, state.bm_name = bm.id, bm.name
    state.dialog = DialogKind.BOOKMARK


def confirm_rename(state: AppState) -> None:
    if state.bm_edit_id:
        store.rename_bookmark(state.bookmarks, state.bm_edit_id, state.bm_name)
        state.dialog = None
        snack("书签已重命名")


def delete_bookmark(state: AppState, bm: Bookmark) -> None:
    store.remove_bookmark(state.bookmarks, bm.id)
    state.bookmarks = [b for b in state.bookmarks if b.id != bm.id]
    snack("书签已删除")
