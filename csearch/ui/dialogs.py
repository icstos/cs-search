"""模态对话框：保存/重命名书签、设置全局热键、自定义大小、设置运行次数。

统一通过 ft.use_dialog 挂载：state.dialog 切换种类，置 None 即关闭。
"""

from __future__ import annotations

import flet as ft

from csearch.constants import DialogKind
from csearch.controller import (
    confirm_bookmark,
    confirm_hotkey,
    confirm_rename,
    confirm_run_count,
    confirm_size,
)
from csearch.state import AppState
from csearch.ui.theme import C


def _dialog_shell(title: str, content: ft.Control, actions: list[ft.Control]) -> ft.AlertDialog:
    return ft.AlertDialog(
        modal=True,
        title=ft.Text(title, size=15, weight=ft.FontWeight.W_600),
        content=content,
        actions=actions,
        actions_alignment=ft.MainAxisAlignment.END,
    )


def _close(state: AppState) -> None:
    state.dialog = None


# --------------------------------------------------------------------- 书签
@ft.component
def BookmarkDialog(state: AppState):
    dialog = ft.use_dialog(None)
    editing = state.bm_edit_id is not None

    def _confirm() -> None:
        (confirm_rename if editing else confirm_bookmark)(state)

    body = ft.Column(
        tight=True,
        spacing=10,
        controls=[
            ft.Text("为当前搜索条件命名，便于一键应用。", size=12, color=C.TEXT_SUB),
            ft.TextField(
                value=state.bm_name,
                label="书签名称",
                autofocus=True,
                dense=True,
                width=320,
                on_change=lambda e: setattr(state, "bm_name", e.control.value),
                on_submit=lambda e: _confirm(),
            ),
        ],
    )
    shell = _dialog_shell(
        "重命名书签" if editing else "保存书签",
        body,
        [
            ft.TextButton("取消", on_click=lambda e: _close(state)),
            ft.FilledButton("确定", icon=ft.Icons.CHECK, on_click=lambda e: _confirm()),
        ],
    )
    ft.use_effect(
        lambda: dialog(shell) if state.dialog == DialogKind.BOOKMARK else dialog(None),
        [state.dialog, state.bm_edit_id],
    )


# --------------------------------------------------------------------- 热键
@ft.component
def HotkeyDialog(state: AppState):
    dialog = ft.use_dialog(None)
    body = ft.Column(
        tight=True,
        spacing=10,
        controls=[
            ft.Text(
                "全局唤起热键，格式：修饰键+按键（如 alt+space、ctrl+shift+f）。\n"
                "留空则禁用全局热键。",
                size=12, color=C.TEXT_SUB,
            ),
            ft.TextField(
                value=state.hotkey_text,
                label="热键组合",
                autofocus=True,
                dense=True,
                width=320,
                on_change=lambda e: setattr(state, "hotkey_text", e.control.value),
                on_submit=lambda e: confirm_hotkey(state),
            ),
        ],
    )
    shell = _dialog_shell(
        "设置全局热键",
        body,
        [
            ft.TextButton("取消", on_click=lambda e: _close(state)),
            ft.FilledButton("确定", icon=ft.Icons.CHECK,
                            on_click=lambda e: confirm_hotkey(state)),
        ],
    )
    ft.use_effect(
        lambda: dialog(shell) if state.dialog == DialogKind.HOTKEY else dialog(None),
        [state.dialog],
    )


# --------------------------------------------------------------------- 自定义大小
@ft.component
def SizeDialog(state: AppState):
    dialog = ft.use_dialog(None)
    body = ft.Column(
        tight=True,
        spacing=10,
        controls=[
            ft.Text("自定义文件大小区间（单位 MB，留空表示不限）：",
                    size=12, color=C.TEXT_SUB),
            ft.Row(
                spacing=8,
                controls=[
                    ft.TextField(
                        value=state.size_min, label="最小 MB", dense=True, width=140,
                        on_change=lambda e: setattr(state, "size_min", e.control.value),
                    ),
                    ft.Text("—", size=14),
                    ft.TextField(
                        value=state.size_max, label="最大 MB", dense=True, width=140,
                        on_change=lambda e: setattr(state, "size_max", e.control.value),
                    ),
                ],
            ),
        ],
    )
    shell = _dialog_shell(
        "自定义大小",
        body,
        [
            ft.TextButton("取消", on_click=lambda e: _close(state)),
            ft.FilledButton("确定", icon=ft.Icons.CHECK,
                            on_click=lambda e: confirm_size(state)),
        ],
    )
    ft.use_effect(
        lambda: dialog(shell) if state.dialog == DialogKind.SIZE else dialog(None),
        [state.dialog],
    )


# --------------------------------------------------------------------- 运行次数
@ft.component
def RunCountDialog(state: AppState):
    dialog = ft.use_dialog(None)
    body = ft.Column(
        tight=True,
        spacing=10,
        controls=[
            ft.Text("手动设置该文件的运行次数（非负整数）：",
                    size=12, color=C.TEXT_SUB),
            ft.TextField(
                value=state.run_count_text,
                label="运行次数",
                autofocus=True,
                dense=True,
                width=200,
                keyboard_type=ft.KeyboardType.NUMBER,
                on_change=lambda e: setattr(state, "run_count_text", e.control.value),
                on_submit=lambda e: confirm_run_count(state),
            ),
        ],
    )
    shell = _dialog_shell(
        "设置运行次数",
        body,
        [
            ft.TextButton("取消", on_click=lambda e: _close(state)),
            ft.FilledButton("确定", icon=ft.Icons.CHECK,
                            on_click=lambda e: confirm_run_count(state)),
        ],
    )
    ft.use_effect(
        lambda: dialog(shell) if state.dialog == DialogKind.RUN_COUNT else dialog(None),
        [state.dialog],
    )


def dialogs(state: AppState) -> None:
    """挂载全部对话框（不返回控件，只通过 use_dialog 注入页面）。"""
    BookmarkDialog(state)
    HotkeyDialog(state)
    SizeDialog(state)
    RunCountDialog(state)
