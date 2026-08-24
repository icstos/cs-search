"""对话框组件：删除确认 / 书签命名 / 热键设置 / 大小区间（全部声明式 use_dialog）。"""

from __future__ import annotations

import asyncio

import flet as ft

from csearch import controller
from csearch.state import AppState


def _page() -> ft.Page:
    return ft.context.page


# ------------------------------------------------------------------ 删除确认
def delete_dialog(state: AppState) -> ft.AlertDialog:
    page = _page()
    n = len(controller.selected_items(state))
    return ft.AlertDialog(
        modal=True,
        title=ft.Text("删除确认"),
        content=ft.Text(
            f"确定删除选中的 {n} 项吗？\n\n"
            "「删除到回收站」可恢复；「永久删除」不可恢复，请谨慎操作。",
            size=13,
        ),
        actions=[
            ft.FilledButton(
                "删除到回收站",
                icon=ft.Icons.DELETE_OUTLINE,
                on_click=lambda e: asyncio.create_task(controller.do_delete(page, state, permanent=False)),
            ),
            ft.OutlinedButton(
                "永久删除",
                icon=ft.Icons.DELETE_FOREVER,
                on_click=lambda e: asyncio.create_task(controller.do_delete(page, state, permanent=True)),
            ),
            ft.TextButton("取消", on_click=lambda e: setattr(state, "dlg_delete", False)),
        ],
        on_dismiss=lambda e: setattr(state, "dlg_delete", False),
    )


# ------------------------------------------------------------------ 书签命名
def bookmark_dialog(state: AppState) -> ft.AlertDialog:
    page = _page()
    editing = state.bookmark_edit_id is not None
    return ft.AlertDialog(
        modal=True,
        title=ft.Text("重命名书签" if editing else "保存书签"),
        content=ft.Column(
            tight=True,
            spacing=8,
            width=320,
            controls=[
                ft.Text(
                    "将当前搜索条件（关键词 + 过滤器）保存为书签，点击即可一键应用。",
                    size=12,
                    color="#5F6368",
                ),
                ft.TextField(
                    label="书签名称",
                    value=state.bm_name,
                    dense=True,
                    autofocus=True,
                    on_change=lambda e: setattr(state, "bm_name", e.control.value),
                    on_submit=lambda e: controller.confirm_bookmark(page, state)
                    if not editing
                    else controller.confirm_rename(page, state),
                ),
            ],
        ),
        actions=[
            ft.FilledButton(
                "保存",
                icon=ft.Icons.SAVE,
                on_click=lambda e: controller.confirm_bookmark(page, state)
                if not editing
                else controller.confirm_rename(page, state),
            ),
            ft.TextButton("取消", on_click=lambda e: setattr(state, "dlg_bookmark", False)),
        ],
        on_dismiss=lambda e: setattr(state, "dlg_bookmark", False),
    )


# ------------------------------------------------------------------ 热键设置
def hotkey_dialog(state: AppState) -> ft.AlertDialog:
    page = _page()
    return ft.AlertDialog(
        modal=True,
        title=ft.Text("全局热键设置"),
        content=ft.Column(
            tight=True,
            spacing=8,
            width=320,
            controls=[
                ft.Text(
                    "格式：修饰键 + 按键，多个用 + 连接。留空则禁用全局热键。\n"
                    "示例：alt+space / ctrl+shift+f / alt+f12",
                    size=12,
                    color="#5F6368",
                ),
                ft.TextField(
                    label="热键组合",
                    value=state.hk_text,
                    dense=True,
                    autofocus=True,
                    on_change=lambda e: setattr(state, "hk_text", e.control.value),
                    on_submit=lambda e: controller.confirm_hotkey(page, state),
                ),
            ],
        ),
        actions=[
            ft.FilledButton("保存", icon=ft.Icons.CHECK, on_click=lambda e: controller.confirm_hotkey(page, state)),
            ft.TextButton("取消", on_click=lambda e: setattr(state, "dlg_hotkey", False)),
        ],
        on_dismiss=lambda e: setattr(state, "dlg_hotkey", False),
    )


# ------------------------------------------------------------------ 大小区间
def size_dialog(state: AppState) -> ft.AlertDialog:
    page = _page()
    return ft.AlertDialog(
        modal=True,
        title=ft.Text("自定义大小区间"),
        content=ft.Column(
            tight=True,
            spacing=8,
            width=320,
            controls=[
                ft.Text("单位：MB，留空表示不限制。例如 最小 1、最大 100。", size=12, color="#5F6368"),
                ft.Row(
                    spacing=10,
                    controls=[
                        ft.TextField(
                            label="最小 (MB)",
                            value=state.size_min,
                            dense=True,
                            expand=True,
                            keyboard_type=ft.KeyboardType.NUMBER,
                            on_change=lambda e: setattr(state, "size_min", e.control.value),
                        ),
                        ft.TextField(
                            label="最大 (MB)",
                            value=state.size_max,
                            dense=True,
                            expand=True,
                            keyboard_type=ft.KeyboardType.NUMBER,
                            on_change=lambda e: setattr(state, "size_max", e.control.value),
                        ),
                    ],
                ),
            ],
        ),
        actions=[
            ft.FilledButton("确定", icon=ft.Icons.CHECK, on_click=lambda e: controller.confirm_size(page, state)),
            ft.TextButton("取消", on_click=lambda e: setattr(state, "dlg_size", False)),
        ],
        on_dismiss=lambda e: setattr(state, "dlg_size", False),
    )
