"""模态对话框：保存/重命名书签、设置全局热键、自定义大小、设置运行次数。

统一通过 ui.use_dialog 挂载：``state.dialog`` 切换种类，置 None 即关闭。
本层零业务逻辑，确定动作全部转发给 ViewModel。
"""

from __future__ import annotations

import ui

from csearch.models.enums import DialogKind
from csearch.view.theme import C
from csearch.viewmodel.context import AppContext


def _dialog_shell(
    title: str, content: ui.Control, actions: list[ui.Control]
) -> ui.ft.AlertDialog:
    """统一的模态外壳。

    为什么取 ``ui.ft.AlertDialog`` 而不是 ``ui.AlertDialog``（改前先读）：
    ui 那个版本是带自家风格的封装（``__post_init__`` 里会把 title/content/actions
    的内边距清零、圆角改成 12、``inset_padding`` 置 0，还会在缺省时自动拼出
    title/content/actions）。CSearch 的四个对话框都是手绘布局，套上去会整体变样。
    这里只需要「一个空白的模态壳」，所以直接取 ui 对外暴露的基类控件，视觉零变化。
    """
    return ui.ft.AlertDialog(
        modal=True,
        title=ui.Text(title, size=15, weight=ui.FontWeight.W_600),
        content=content,
        actions=actions,
        actions_alignment=ui.MainAxisAlignment.END,
    )


def _close(ctx: AppContext) -> None:
    ctx.state.dialog = None


# --------------------------------------------------------------------- 书签
@ui.component
def BookmarkDialog(ctx: AppContext):
    state = ctx.state
    dialog = ui.use_dialog(None)
    editing = state.bm_edit_id is not None

    def _confirm() -> None:
        (ctx.bookmarks.confirm_rename if editing else ctx.bookmarks.confirm_save)()

    body = ui.Column(
        tight=True,
        spacing=10,
        controls=[
            ui.Text("为当前搜索条件命名，便于一键应用。", size=12, color=C.TEXT_SUB),
            ui.TextField(
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
            ui.TextButton("取消", on_click=lambda e: _close(ctx)),
            ui.FilledButton("确定", icon=ui.Icons.CHECK, on_click=lambda e: _confirm()),
        ],
    )
    ui.use_effect(
        lambda: dialog(shell) if state.dialog == DialogKind.BOOKMARK else dialog(None),
        [state.dialog, state.bm_edit_id],
    )


# --------------------------------------------------------------------- 热键
@ui.component
def HotkeyDialog(ctx: AppContext):
    state = ctx.state
    dialog = ui.use_dialog(None)
    body = ui.Column(
        tight=True,
        spacing=10,
        controls=[
            ui.Text(
                "全局唤起热键，格式：修饰键+按键（如 alt+space、ctrl+shift+f），\n"
                "必须包含至少一个非修饰键（纯修饰键会退化成「按一下就唤起」）。\n"
                "留空则禁用全局热键。",
                size=12, color=C.TEXT_SUB,
            ),
            ui.TextField(
                value=state.hotkey_text,
                label="热键组合",
                autofocus=True,
                dense=True,
                width=320,
                on_change=lambda e: setattr(state, "hotkey_text", e.control.value),
                on_submit=lambda e: ctx.settings.confirm_hotkey(),
            ),
        ],
    )
    shell = _dialog_shell(
        "设置全局热键",
        body,
        [
            ui.TextButton("取消", on_click=lambda e: _close(ctx)),
            ui.FilledButton("确定", icon=ui.Icons.CHECK,
                            on_click=lambda e: ctx.settings.confirm_hotkey()),
        ],
    )
    ui.use_effect(
        lambda: dialog(shell) if state.dialog == DialogKind.HOTKEY else dialog(None),
        [state.dialog],
    )


# --------------------------------------------------------------------- 自定义大小
@ui.component
def SizeDialog(ctx: AppContext):
    state = ctx.state
    dialog = ui.use_dialog(None)
    body = ui.Column(
        tight=True,
        spacing=10,
        controls=[
            ui.Text("自定义文件大小区间（单位 MB，留空表示不限）：",
                    size=12, color=C.TEXT_SUB),
            ui.Row(
                spacing=8,
                controls=[
                    ui.TextField(
                        value=state.size_min, label="最小 MB", dense=True, width=140,
                        on_change=lambda e: setattr(state, "size_min", e.control.value),
                    ),
                    ui.Text("—", size=14),
                    ui.TextField(
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
            ui.TextButton("取消", on_click=lambda e: _close(ctx)),
            ui.FilledButton("确定", icon=ui.Icons.CHECK,
                            on_click=lambda e: ctx.settings.confirm_size()),
        ],
    )
    ui.use_effect(
        lambda: dialog(shell) if state.dialog == DialogKind.SIZE else dialog(None),
        [state.dialog],
    )


# --------------------------------------------------------------------- 运行次数
@ui.component
def RunCountDialog(ctx: AppContext):
    state = ctx.state
    dialog = ui.use_dialog(None)
    body = ui.Column(
        tight=True,
        spacing=10,
        controls=[
            ui.Text("手动设置该文件的运行次数（非负整数）：",
                    size=12, color=C.TEXT_SUB),
            ui.TextField(
                value=state.run_count_text,
                label="运行次数",
                autofocus=True,
                dense=True,
                width=200,
                keyboard_type=ui.KeyboardType.NUMBER,
                on_change=lambda e: setattr(state, "run_count_text", e.control.value),
                on_submit=lambda e: ctx.actions.confirm_run_count(),
            ),
        ],
    )
    shell = _dialog_shell(
        "设置运行次数",
        body,
        [
            ui.TextButton("取消", on_click=lambda e: _close(ctx)),
            ui.FilledButton("确定", icon=ui.Icons.CHECK,
                            on_click=lambda e: ctx.actions.confirm_run_count()),
        ],
    )
    ui.use_effect(
        lambda: dialog(shell) if state.dialog == DialogKind.RUN_COUNT else dialog(None),
        [state.dialog],
    )


def dialogs(ctx: AppContext) -> None:
    """挂载全部对话框（不返回控件，只通过 use_dialog 注入页面）。"""
    BookmarkDialog(ctx)
    HotkeyDialog(ctx)
    SizeDialog(ctx)
    RunCountDialog(ctx)
