"""文件动作：打开 / 定位 / 复制路径 / 复制文件名 / 删除 / 打开文件夹 / 运行次数。

全部系统调用经 asyncio.to_thread 入线程池；删除默认移入回收站、无需确认，
删除后本地即时移除并选中下一项，再后台重查与索引同步。
"""

from __future__ import annotations

import asyncio
import webbrowser

from csearch import history, ops
from csearch.constants import DialogKind
from csearch.controller.common import selected_items, snack
from csearch.controller.search import run_search, scroll_results
from csearch.state import AppState


def _refresh_run_counts(state: AppState, paths: list[str]) -> None:
    """打开/设置次数后批量回查并本地更新显示值（单次查询，避免逐行查库）。"""
    touched = {p for p in paths if p}
    if not touched:
        return
    counts = history.get_counts(list(touched))
    changed = False
    for row in state.results:
        if row.full_path in touched:
            row.run_count = counts.get(row.full_path, row.run_count)
            changed = True
    if changed:
        state.results = list(state.results)  # 整体替换触发重绘


def request_run_count(state: AppState, index: int) -> None:
    """右键设置运行次数：打开输入对话框。"""
    if 0 <= index < len(state.results):
        item = state.results[index]
        state.run_count_path = item.full_path
        state.run_count_text = str(item.run_count)
        state.dialog = DialogKind.RUN_COUNT


def confirm_run_count(state: AppState) -> None:
    """确认设置运行次数。"""
    try:
        count = max(0, int(state.run_count_text.strip() or "0"))
    except ValueError:
        snack("请输入有效的非负整数")
        return
    if not state.run_count_path:
        return
    history.set_count(state.run_count_path, count)
    _refresh_run_counts(state, [state.run_count_path])
    state.dialog = None
    snack(f"已设置运行次数：{count}")


async def open_selected(state: AppState) -> None:
    items = selected_items(state)
    if not items:
        snack("未选中任何文件")
        return
    errors = await asyncio.to_thread(ops.open_items, items)
    if errors:
        snack(f"打开失败：{errors[0]}")
        return
    opened = [i.full_path for i in items]
    await asyncio.to_thread(history.increment, opened)
    _refresh_run_counts(state, opened)


async def reveal_selected(state: AppState) -> None:
    items = selected_items(state)
    if not items:
        snack("未选中任何文件")
        return
    errors = await asyncio.to_thread(ops.reveal_items, items)
    if errors:
        snack(f"定位失败：{errors[0]}")


async def copy_paths(state: AppState) -> None:
    items = selected_items(state)
    if not items:
        snack("未选中任何文件")
        return
    error = await asyncio.to_thread(ops.copy_paths, items)
    snack(f"复制失败：{error}" if error else f"已复制 {len(items)} 个完整路径")


async def copy_names(state: AppState) -> None:
    items = selected_items(state)
    if not items:
        snack("未选中任何文件")
        return
    error = await asyncio.to_thread(ops.copy_names, items)
    snack(f"复制失败：{error}" if error else f"已复制 {len(items)} 个文件名")


async def open_folder(state: AppState, index: int) -> None:
    """双击路径列：在资源管理器中打开对应文件夹。"""
    if 0 <= index < len(state.results):
        error = await asyncio.to_thread(ops.open_folder, state.results[index].path)
        if error:
            snack(f"打开文件夹失败：{error}")


async def delete_selected(state: AppState) -> None:
    """删除选中项到回收站（无需确认），本地即时移除并选中下一项，随后后台重查同步。"""
    items = selected_items(state)
    if not items:
        snack("未选中任何文件")
        return
    first = min(state.selected)  # 首个被删行位置：移除后该位置即「下一项」
    deleted_paths, errors = await asyncio.to_thread(ops.delete_to_trash, items)
    if deleted_paths:
        gone = set(deleted_paths)
        state.results = [r for r in state.results if r.full_path not in gone]
        state.total = max(0, state.total - len(deleted_paths))
        if state.results:
            target = min(first, len(state.results) - 1)
            state.selected, state.anchor = {target}, target
            asyncio.create_task(scroll_results(state, None, row=target))
        else:
            state.selected, state.anchor = set(), -1
    snack(
        f"已移入回收站 {len(deleted_paths)} 项"
        + (f"，失败：{errors[0]}" if errors else "")
    )
    if deleted_paths:
        asyncio.create_task(run_search(state, keep_selection=True))


def launch_everything() -> None:
    """一键启动 Everything；找不到程序则打开下载页。"""
    if ops.launch_everything():
        snack("正在启动 Everything…")
    else:
        webbrowser.open("https://www.voidtools.com/zh-cn/downloads/")
