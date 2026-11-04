"""模态对话框：保存/重命名书签、设置全局热键、自定义大小、设置运行次数。

``state.dialog`` 决定「这一帧显示哪个对话框」，置 None 即关闭。
本层零业务逻辑，确定动作全部转发给 ViewModel。

两个实现要点（改前先读）：

1. ``ui.use_dialog`` 在 flet 1.0 里是**渲染期钩子**：调用它时把「要显示的控件」
   作为参数传进去（不显示时传 ``None``），它本身不返回任何东西。写成
   ``show = ui.use_dialog(None); show(shell)`` 是旧 API 的用法 —— ``show`` 是 None，
   点开会抛 TypeError，表现为「按钮点了没反应」。
2. 对话框壳**按打开的那一次缓存**：壳里的输入框是受控的，如果每帧重建控件，
   每敲一个字都会把 value 下发回客户端，和搜索框是同一类输入法（IME）问题
   （组合中的拼音会被重置）。缓存同一实例后，重复提交的 diff 为零。
"""

from __future__ import annotations

import ui

from csearch.models.enums import DialogKind
from csearch.view.theme import FS, FW, SP, TEXT, TEXT_SUB, outline_field
from csearch.viewmodel.context import AppContext

_FORM_WIDTH = 400

#: 当前挂载的 (对话框种类, 壳控件)。关闭时清空，下次打开按最新状态重建。
_mounted: tuple[DialogKind, ui.AlertDialog] | None = None


def _dialog_shell(
    title: str, content: ui.Control, actions: list[ui.Control]
) -> ui.AlertDialog:
    """统一的模态外壳：标题留白 + 正文区 + 右对齐动作区。

    借 cs-ui ``AlertDialog`` 的模态外壳（12px 圆角、自家动作区内边距），
    标题与正文自己排版 —— 那四个都是表单，需要能塞任意控件。
    """
    return ui.AlertDialog(
        modal=True,
        title=ui.Container(
            content=ui.Text(title, size=FS["title"], weight=FW["semibold"], color=TEXT),
            padding=ui.Padding(SP["6"], SP["5"], SP["6"], SP["1"]),
        ),
        content=ui.Container(
            content=content,
            width=_FORM_WIDTH,
            padding=ui.Padding(SP["6"], 0, SP["6"], SP["2"]),
        ),
        actions=actions,
        actions_alignment=ui.MainAxisAlignment.END,
    )


def _hint(text: str) -> ui.Control:
    return ui.Text(text, size=FS["small"], color=TEXT_SUB)


def _cancel(ctx: AppContext) -> ui.Control:
    return ui.TextButton("取消", on_click=lambda e: _close(ctx))


def _confirm(label: str, on_click) -> ui.Control:
    return ui.FilledButton(label, icon=ui.Icons.CHECK, on_click=on_click)


def _close(ctx: AppContext) -> None:
    ctx.state.dialog = None


# --------------------------------------------------------------------- 各对话框
def _bookmark_shell(ctx: AppContext) -> ui.AlertDialog:
    state = ctx.state
    editing = state.bm_edit_id is not None

    def _confirm_action() -> None:
        (ctx.bookmarks.confirm_rename if editing else ctx.bookmarks.confirm_save)()

    return _dialog_shell(
        "重命名书签" if editing else "保存书签",
        ui.Column(
            tight=True,
            spacing=SP["3"],
            controls=[
                _hint("为当前搜索条件命名，之后一键复用。"),
                outline_field(
                    value=state.bm_name,
                    label="书签名称",
                    autofocus=True,
                    width=_FORM_WIDTH - SP["12"],
                    on_change=lambda e: setattr(state, "bm_name", e.control.value),
                    on_submit=lambda e: _confirm_action(),
                ),
            ],
        ),
        [
            _cancel(ctx),
            _confirm("确定", lambda e: _confirm_action()),
        ],
    )


def _hotkey_shell(ctx: AppContext) -> ui.AlertDialog:
    state = ctx.state
    return _dialog_shell(
        "设置全局热键",
        ui.Column(
            tight=True,
            spacing=SP["3"],
            controls=[
                _hint(
                    "修饰键 + 按键，如 alt+space、ctrl+shift+f。\n"
                    "必须包含至少一个非修饰键（纯修饰键会退化成「按一下即唤起」）。\n"
                    "留空则禁用全局热键。"
                ),
                outline_field(
                    value=state.hotkey_text,
                    label="热键组合",
                    autofocus=True,
                    width=_FORM_WIDTH - SP["12"],
                    on_change=lambda e: setattr(state, "hotkey_text", e.control.value),
                    on_submit=lambda e: ctx.settings.confirm_hotkey(),
                ),
            ],
        ),
        [
            _cancel(ctx),
            _confirm("确定", lambda e: ctx.settings.confirm_hotkey()),
        ],
    )


def _size_shell(ctx: AppContext) -> ui.AlertDialog:
    state = ctx.state
    field_width = (_FORM_WIDTH - SP["12"] - SP["3"]) / 2
    return _dialog_shell(
        "自定义大小",
        ui.Column(
            tight=True,
            spacing=SP["3"],
            controls=[
                _hint("按文件大小过滤，单位 MB；留空表示不限。"),
                ui.Row(
                    spacing=SP["3"],
                    vertical_alignment=ui.CrossAxisAlignment.CENTER,
                    controls=[
                        outline_field(
                            value=state.size_min,
                            label="最小",
                            width=field_width,
                            on_change=lambda e: setattr(
                                state, "size_min", e.control.value
                            ),
                        ),
                        _hint("—"),
                        outline_field(
                            value=state.size_max,
                            label="最大",
                            width=field_width,
                            on_change=lambda e: setattr(
                                state, "size_max", e.control.value
                            ),
                        ),
                    ],
                ),
            ],
        ),
        [
            _cancel(ctx),
            _confirm("确定", lambda e: ctx.settings.confirm_size()),
        ],
    )


def _run_count_shell(ctx: AppContext) -> ui.AlertDialog:
    state = ctx.state
    return _dialog_shell(
        "设置运行次数",
        ui.Column(
            tight=True,
            spacing=SP["3"],
            controls=[
                _hint("手动设置该文件的运行次数（非负整数）。"),
                outline_field(
                    value=state.run_count_text,
                    label="运行次数",
                    autofocus=True,
                    width=_FORM_WIDTH - SP["12"],
                    keyboard_type=ui.KeyboardType.NUMBER,
                    on_change=lambda e: setattr(
                        state, "run_count_text", e.control.value
                    ),
                    on_submit=lambda e: ctx.actions.confirm_run_count(),
                ),
            ],
        ),
        [
            _cancel(ctx),
            _confirm("确定", lambda e: ctx.actions.confirm_run_count()),
        ],
    )


_BUILDERS = {
    DialogKind.BOOKMARK: _bookmark_shell,
    DialogKind.HOTKEY: _hotkey_shell,
    DialogKind.SIZE: _size_shell,
    DialogKind.RUN_COUNT: _run_count_shell,
}


# --------------------------------------------------------------------- 挂载
def dialogs(ctx: AppContext) -> None:
    """在根组件渲染期挂载「当前该显示的对话框」（不返回控件）。

    为什么是普通函数而不是 ``@ui.component``：对话框壳没有视觉产出，包成组件
    再塞进布局会得到一个全尺寸空容器 —— flet 里空 Container 在 Stack 的松约束
    下会撑满并参与命中测试，把整张列表的点击全吞掉（结果行「点了没反应」的经典
    成因）。直接由根组件调用，钩子仍挂在根组件的 hook 序列上，顺序固定。
    """
    global _mounted
    kind = ctx.state.dialog
    if kind is None:
        _mounted = None
        ui.use_dialog(None)
        return
    if _mounted is None or _mounted[0] is not kind:
        _mounted = (kind, _BUILDERS[kind](ctx))
    ui.use_dialog(_mounted[1])
