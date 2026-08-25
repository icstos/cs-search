"""对话框组件：删除确认 / 书签命名 / 热键设置 / 大小区间（声明式 use_dialog）。"""

from __future__ import annotations

import flet as ft

from csearch import logic
from csearch.state import AppState


def dialogs(state: AppState) -> None:
    """根据 state.dialog 挂载对应对话框（None = 全部关闭）。"""
    ft.use_dialog(_delete(state) if state.dialog == "delete" else None)
    ft.use_dialog(_bookmark(state) if state.dialog == "bookmark" else None)
    ft.use_dialog(_hotkey(state) if state.dialog == "hotkey" else None)
    ft.use_dialog(_size(state) if state.dialog == "size" else None)
    ft.use_dialog(_run_count(state) if state.dialog == "run_count" else None)


def _run_count(state: AppState) -> ft.AlertDialog:
    return ft.AlertDialog(
        modal=True,
        title=ft.Text("设置运行次数"),
        content=ft.Column(
            tight=True, spacing=8, width=320,
            controls=[
                ft.Text("为该文件设置打开/运行次数（用于次数列展示）。",
                        size=12, color="#5F6368"),
                ft.TextField(
                    label="运行次数",
                    value=state.run_count_text,
                    dense=True,
                    autofocus=True,
                    keyboard_type=ft.KeyboardType.NUMBER,
                    on_change=lambda e: setattr(state, "run_count_text", e.control.value),
                    on_submit=lambda e: logic.confirm_run_count(state),
                ),
            ],
        ),
        actions=[
            ft.FilledButton("确定", icon=ft.Icons.CHECK, on_click=lambda e: logic.confirm_run_count(state)),
            ft.TextButton("取消", on_click=_close(state)),
        ],
        on_dismiss=_close(state),
    )


def _close(state: AppState):
    return lambda e: setattr(state, "dialog", None)


def _delete(state: AppState) -> ft.AlertDialog:
    count = len(logic.selected_items(state))
    return ft.AlertDialog(
        modal=True,
        title=ft.Text("删除确认"),
        content=ft.Text(
            f"确定删除选中的 {count} 项吗？\n\n"
            "「删除到回收站」可恢复；「永久删除」不可恢复，请谨慎操作。",
            size=13,
        ),
        actions=[
            ft.FilledButton("删除到回收站", icon=ft.Icons.DELETE_OUTLINE,
                            on_click=lambda e: logic.do_delete(state, False)),
            ft.OutlinedButton("永久删除", icon=ft.Icons.DELETE_FOREVER,
                              on_click=lambda e: logic.do_delete(state, True)),
            ft.TextButton("取消", on_click=_close(state)),
        ],
        on_dismiss=_close(state),
    )


def _bookmark(state: AppState) -> ft.AlertDialog:
    editing = state.bm_edit_id is not None
    return ft.AlertDialog(
        modal=True,
        title=ft.Text("重命名书签" if editing else "保存书签"),
        content=ft.Column(
            tight=True, spacing=8, width=320,
            controls=[
                ft.Text("将当前搜索条件（关键词 + 过滤器）保存为书签，点击即可一键应用。",
                        size=12, color="#5F6368"),
                ft.TextField(
                    label="书签名称",
                    value=state.bm_name,
                    dense=True,
                    autofocus=True,
                    on_change=lambda e: setattr(state, "bm_name", e.control.value),
                    on_submit=lambda e: logic.confirm_rename(state) if editing else logic.confirm_bookmark(state),
                ),
            ],
        ),
        actions=[
            ft.FilledButton("保存", icon=ft.Icons.SAVE,
                            on_click=lambda e: logic.confirm_rename(state) if editing else logic.confirm_bookmark(state)),
            ft.TextButton("取消", on_click=_close(state)),
        ],
        on_dismiss=_close(state),
    )


def _hotkey(state: AppState) -> ft.AlertDialog:
    return ft.AlertDialog(
        modal=True,
        title=ft.Text("全局热键设置"),
        content=ft.Column(
            tight=True, spacing=8, width=320,
            controls=[
                ft.Text("格式：修饰键 + 按键，多个用 + 连接。留空则禁用全局热键。\n"
                        "示例：alt+space / ctrl+shift+f / alt+f12", size=12, color="#5F6368"),
                ft.TextField(
                    label="热键组合",
                    value=state.hotkey_text,
                    dense=True,
                    autofocus=True,
                    on_change=lambda e: setattr(state, "hotkey_text", e.control.value),
                    on_submit=lambda e: logic.confirm_hotkey(state),
                ),
            ],
        ),
        actions=[
            ft.FilledButton("保存", icon=ft.Icons.CHECK, on_click=lambda e: logic.confirm_hotkey(state)),
            ft.TextButton("取消", on_click=_close(state)),
        ],
        on_dismiss=_close(state),
    )


def _size(state: AppState) -> ft.AlertDialog:
    return ft.AlertDialog(
        modal=True,
        title=ft.Text("自定义大小区间"),
        content=ft.Column(
            tight=True, spacing=8, width=320,
            controls=[
                ft.Text("单位：MB，留空表示不限制。例如 最小 1、最大 100。", size=12, color="#5F6368"),
                ft.Row(
                    spacing=10,
                    controls=[
                        ft.TextField(label="最小 (MB)", value=state.size_min, dense=True, expand=True,
                                     keyboard_type=ft.KeyboardType.NUMBER,
                                     on_change=lambda e: setattr(state, "size_min", e.control.value)),
                        ft.TextField(label="最大 (MB)", value=state.size_max, dense=True, expand=True,
                                     keyboard_type=ft.KeyboardType.NUMBER,
                                     on_change=lambda e: setattr(state, "size_max", e.control.value)),
                    ],
                ),
            ],
        ),
        actions=[
            ft.FilledButton("确定", icon=ft.Icons.CHECK, on_click=lambda e: logic.confirm_size(state)),
            ft.TextButton("取消", on_click=_close(state)),
        ],
        on_dismiss=_close(state),
    )
