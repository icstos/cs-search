"""CSearch 介绍站点（单文件 ui 应用，桌面 / Web 通用）。

运行：
    flet run app.py          # 桌面窗口
    flet run -d -w app.py    # 浏览器（-w web）

特性：单文件、无外部资源；顶栏导航平滑滚动、悬停反馈、响应式栅格、首屏淡入、
明暗主题切换（本地 JSON 持久化）、命令一键复制。
适配目标版本：cs-ui 0.1.1（底层 Flet 1.0.5）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import ui

# 主题偏好持久化（与主程序共用 %APPDATA%/CSearch 目录；缺失时静默降级）
_PREF_PATH = Path(os.environ.get("APPDATA", Path.home())) / "CSearch" / "landing.json"

# 强调色（主程序同款蓝）
_ACCENT = "#1A73E8"
_ACCENT_SOFT = "#E8F0FE"
_GITHUB = "https://github.com/"

_PALETTE = {
    "light": {
        "bg": "#FFFFFF",
        "surface": "#F7F8FA",
        "card": "#FFFFFF",
        "text": "#202124",
        "sub": "#5F6368",
        "hint": "#9AA0A6",
        "border": "#E4E7ED",
        "gradient": ["#F4F8FF", "#EAF1FE", "#FFFFFF"],
        "shadow": "#1A73E8",
        "nav_bg": ui.Colors.with_opacity(0.82, "#FFFFFF"),
    },
    "dark": {
        "bg": "#0F1115",
        "surface": "#171A21",
        "card": "#1C2029",
        "text": "#E8EAED",
        "sub": "#9AA0A6",
        "hint": "#5F6368",
        "border": "#2A2F3A",
        "gradient": ["#10141C", "#131A28", "#0F1115"],
        "shadow": "#000000",
        "nav_bg": ui.Colors.with_opacity(0.82, "#14171E"),
    },
}


def _load_theme() -> str:
    try:
        data = json.loads(_PREF_PATH.read_text(encoding="utf-8"))
        return data.get("theme", "light")
    except Exception:  # noqa: BLE001
        return "light"


def _save_theme(theme: str) -> None:
    try:
        _PREF_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PREF_PATH.write_text(json.dumps({"theme": theme}), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _copy_text(text: str) -> bool:
    """复制到剪贴板：优先 pyperclip（桌面），失败返回 False。"""
    try:
        import pyperclip

        pyperclip.copy(text)
        return True
    except Exception:  # noqa: BLE001
        return False


class LandingSite:
    """介绍站点：持有页面与主题状态，按区块构建界面。"""

    def __init__(self, page: ui.Page) -> None:
        self.page = page
        self.theme = _load_theme()
        self.scroll_offset = 0.0
        self.menu_open = False
        self._mobile_menu: ui.Container | None = None

    # ------------------------------------------------------------------ 基础
    @property
    def p(self) -> dict[str, Any]:
        return _PALETTE[self.theme]

    def setup(self) -> None:
        self.page.title = "CSearch - Everything 极速文件搜索"
        self.page.padding = 0
        self.page.spacing = 0
        self.page.scroll = ui.ScrollMode.AUTO
        self.page.theme_mode = (
            ui.ThemeMode.DARK if self.theme == "dark" else ui.ThemeMode.LIGHT
        )
        self.page.bgcolor = self.p["bg"]
        self.page.on_scroll = self._on_scroll
        self.page.on_resize = lambda e: self.render()

    def render(self) -> None:
        """整页重建（仅在主题切换 / 菜单开合 / 窗口尺寸变化时触发）。"""
        self.page.controls.clear()
        self.page.bgcolor = self.p["bg"]
        self.page.add(
            self._navbar(),
            self._hero(),
            self._features(),
            self._architecture(),
            self._quickstart(),
            self._footer(),
        )
        self.page.update()
        self.page.run_task(self._hero_fade)

    def snack(self, text: str) -> None:
        self.page.show_dialog(ui.SnackBar(ui.Text(text, size=13), duration=1600))

    def _goto(self, key: str) -> None:
        self.page.scroll_to(
            scroll_key=key, duration=320, curve=ui.AnimationCurve.EASE_OUT
        )

    def _on_scroll(self, e) -> None:
        self.scroll_offset = float(e.pixels or 0)

    # ------------------------------------------------------------------ 通用组件
    def _section_title(self, eyebrow: str, title: str, desc: str) -> ui.Control:
        return ui.Column(
            horizontal_alignment=ui.CrossAxisAlignment.CENTER,
            spacing=6,
            controls=[
                ui.Text(eyebrow, size=12, weight=ui.FontWeight.W_700, color=_ACCENT),
                ui.Text(
                    title,
                    size=26,
                    weight=ui.FontWeight.W_800,
                    color=self.p["text"],
                    text_align=ui.TextAlign.CENTER,
                ),
                ui.Text(
                    desc,
                    size=14,
                    color=self.p["sub"],
                    text_align=ui.TextAlign.CENTER,
                    width=640,
                ),
            ],
        )

    def _card(self, content: ui.Control, *, pad: int = 20) -> ui.Control:
        return ui.Container(
            bgcolor=self.p["card"],
            border_radius=14,
            padding=pad,
            border=ui.Border.all(1, self.p["border"]),
            shadow=ui.BoxShadow(
                0, 6, 18, ui.Colors.with_opacity(0.06, self.p["shadow"])
            ),
            content=content,
        )

    # ------------------------------------------------------------------ 导航
    def _nav_link(self, label: str, key: str) -> ui.Control:
        return ui.TextButton(
            content=ui.Text(label, size=13, color=self.p["sub"]),
            on_click=lambda e: self._goto(key),
        )

    def _theme_button(self) -> ui.Control:
        dark = self.theme == "dark"
        return ui.IconButton(
            ui.Icons.DARK_MODE if not dark else ui.Icons.LIGHT_MODE,
            icon_size=20,
            tooltip="切换明暗主题",
            icon_color=self.p["sub"],
            on_click=lambda e: self._toggle_theme(),
        )

    def _navbar(self) -> ui.Control:
        wide = (self.page.window.width or 1200) >= 860
        links = [
            self._nav_link("功能特性", "features"),
            self._nav_link("架构", "architecture"),
            self._nav_link("快速开始", "quickstart"),
        ]
        brand = ui.Row(
            spacing=8,
            controls=[
                ui.Icon(ui.Icons.SPEED, color=_ACCENT, size=24),
                ui.Text(
                    "CSearch", size=18, weight=ui.FontWeight.W_800, color=self.p["text"]
                ),
            ],
        )
        if wide:
            trailing: ui.Control = ui.Row(
                spacing=4,
                controls=[
                    *links,
                    self._theme_button(),
                    ui.FilledButton(
                        content=ui.Text("GitHub", size=13, weight=ui.FontWeight.W_600),
                        icon=ui.Icons.CODE,
                        url=_GITHUB,
                    ),
                ],
            )
        else:
            trailing = ui.Row(
                spacing=2,
                controls=[
                    self._theme_button(),
                    ui.IconButton(
                        ui.Icons.MENU,
                        icon_size=22,
                        icon_color=self.p["text"],
                        on_click=lambda e: self._toggle_mobile_menu(),
                    ),
                ],
            )
        return ui.Container(
            bgcolor=self.p["nav_bg"],
            padding=ui.Padding(24, 10, 24, 10),
            border=ui.Border(bottom=ui.BorderSide(1, self.p["border"])),
            content=ui.Row(
                alignment=ui.MainAxisAlignment.SPACE_BETWEEN,
                controls=[brand, trailing],
            ),
        )

    def _toggle_mobile_menu(self) -> None:
        self.menu_open = not self.menu_open
        if self._mobile_menu is not None:
            try:
                self.page.overlay.remove(self._mobile_menu)
            except Exception:  # noqa: BLE001
                pass
            self._mobile_menu = None
        if self.menu_open:
            self._mobile_menu = ui.Container(
                bgcolor=self.p["card"],
                border_radius=10,
                padding=10,
                top=58,
                right=16,
                width=180,
                border=ui.Border.all(1, self.p["border"]),
                content=ui.Column(
                    tight=True,
                    controls=[
                        self._nav_link("功能特性", "features"),
                        self._nav_link("架构", "architecture"),
                        self._nav_link("快速开始", "quickstart"),
                    ],
                ),
            )
            self.page.overlay.append(self._mobile_menu)
        self.page.update()

    def _toggle_theme(self) -> None:
        self.theme = "dark" if self.theme == "light" else "light"
        _save_theme(self.theme)
        self.page.theme_mode = (
            ui.ThemeMode.DARK if self.theme == "dark" else ui.ThemeMode.LIGHT
        )
        self.render()

    # ------------------------------------------------------------------ 首屏
    def _hero(self) -> ui.Control:
        self._hero_title = ui.Text(
            "Everything 内核 · 毫秒级文件搜索",
            size=40,
            weight=ui.FontWeight.W_800,
            color=self.p["text"],
            text_align=ui.TextAlign.CENTER,
            opacity=0,
            animate_opacity=ui.Animation(700, ui.AnimationCurve.EASE_OUT),
        )
        self._hero_sub = ui.Text(
            "基于 Everything 1.5 SDK 与 cs-ui 构建的桌面文件搜索工具：\n"
            "原生 IPC 直查、分页流式渲染、全局热键、系统托盘、运行历史与书签，开箱即用。",
            size=15,
            color=self.p["sub"],
            text_align=ui.TextAlign.CENTER,
            width=720,
            opacity=0,
            animate_opacity=ui.Animation(900, ui.AnimationCurve.EASE_OUT),
        )
        stats = ui.Row(
            alignment=ui.MainAxisAlignment.CENTER,
            spacing=32,
            controls=[
                self._stat("15~80ms", "29 万结果首屏"),
                self._stat("200/页", "分页流式加载"),
                self._stat("Alt+Space", "全局热键唤起"),
            ],
        )
        actions = ui.Row(
            alignment=ui.MainAxisAlignment.CENTER,
            spacing=12,
            controls=[
                ui.FilledButton(
                    content=ui.Text("快速开始", size=14, weight=ui.FontWeight.W_700),
                    icon=ui.Icons.ROCKET_LAUNCH,
                    style=ui.ButtonStyle(padding=ui.Padding(20, 12, 20, 12)),
                    on_click=lambda e: self._goto("quickstart"),
                ),
                ui.OutlinedButton(
                    content=ui.Text("查看架构", size=14),
                    icon=ui.Icons.ACCOUNT_TREE,
                    style=ui.ButtonStyle(padding=ui.Padding(20, 12, 20, 12)),
                    on_click=lambda e: self._goto("architecture"),
                ),
            ],
        )
        glow = ui.Container(
            expand=True,
            gradient=ui.RadialGradient(
                center=ui.Alignment(0.9, 0.1),
                radius=1.2,
                colors=[
                    ui.Colors.with_opacity(0.10, _ACCENT),
                    ui.Colors.with_opacity(0, _ACCENT),
                ],
            ),
        )
        body = ui.Column(
            horizontal_alignment=ui.CrossAxisAlignment.CENTER,
            spacing=20,
            controls=[self._hero_title, self._hero_sub, actions, stats],
        )
        return ui.Container(
            gradient=ui.LinearGradient(
                begin=ui.Alignment(-1, -1),
                end=ui.Alignment(1, 1),
                colors=self.p["gradient"],
            ),
            padding=ui.Padding(24, 72, 24, 72),
            content=ui.Stack(controls=[glow, body]),
        )

    def _stat(self, value: str, label: str) -> ui.Control:
        return ui.Column(
            horizontal_alignment=ui.CrossAxisAlignment.CENTER,
            spacing=2,
            controls=[
                ui.Text(value, size=22, weight=ui.FontWeight.W_800, color=_ACCENT),
                ui.Text(label, size=12, color=self.p["sub"]),
            ],
        )

    async def _hero_fade(self) -> None:
        self._hero_title.opacity = 1
        self._hero_sub.opacity = 1
        try:
            self.page.update()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ 功能
    def _feature(self, icon: str, title: str, desc: str) -> ui.Control:
        return self._card(
            ui.Column(
                spacing=10,
                controls=[
                    ui.Container(
                        width=40,
                        height=40,
                        border_radius=10,
                        bgcolor=_ACCENT_SOFT,
                        alignment=ui.Alignment(0, 0),
                        content=ui.Icon(icon, color=_ACCENT, size=22),
                    ),
                    ui.Text(
                        title, size=15, weight=ui.FontWeight.W_700, color=self.p["text"]
                    ),
                    ui.Text(desc, size=12.5, color=self.p["sub"]),
                ],
            )
        )

    def _features(self) -> ui.Control:
        items = [
            (
                "BOLT",
                "极速查询",
                "Everything IPC 直查 MFT 索引，分页限制传输量，数十万结果毫秒返回。",
            ),
            (
                "VIEW_IN_AR",
                "流式渲染",
                "结果分片落地、批间让出事件循环，打字与滚轮始终跟手，不卡白屏。",
            ),
            (
                "KEYBOARD",
                "键盘优先",
                "全局热键唤起，↑↓ 选择、Enter 打开、Ctrl+D 复制路径，双手不离键盘。",
            ),
            (
                "BOOKMARK",
                "书签过滤",
                "分类/时间/大小组合条件可存为书签，一键应用；支持 Everything 原生语法与正则。",
            ),
            (
                "HISTORY",
                "运行历史",
                "SQLite 记录每个文件的打开次数，回车优先打开高频文件，并可按列排序。",
            ),
            (
                "EXPLORE",
                "系统集成",
                "系统托盘、删除入回收站、资源管理器定位、多屏防丢窗与滚轮桥兜底。",
            ),
        ]
        cards = [
            ui.Container(col={"sm": 12, "md": 6, "lg": 4}, content=self._feature(*it))
            for it in items
        ]
        return ui.Container(
            key="features",
            padding=ui.Padding(24, 56, 24, 56),
            content=ui.Column(
                spacing=24,
                horizontal_alignment=ui.CrossAxisAlignment.CENTER,
                controls=[
                    self._section_title(
                        "FEATURES", "功能特性", "为高频文件检索场景做的端到端优化"
                    ),
                    ui.ResponsiveRow(controls=cards, run_spacing=16, spacing=16),
                ],
            ),
        )

    # ------------------------------------------------------------------ 架构
    def _arch_step(self, index: int, title: str, desc: str) -> ui.Control:
        return ui.Row(
            spacing=14,
            controls=[
                ui.Container(
                    width=34,
                    height=34,
                    border_radius=17,
                    bgcolor=_ACCENT,
                    alignment=ui.Alignment(0, 0),
                    content=ui.Text(
                        str(index), color="#FFFFFF", weight=ui.FontWeight.W_800, size=14
                    ),
                ),
                ui.Column(
                    spacing=2,
                    controls=[
                        ui.Text(
                            title,
                            size=14,
                            weight=ui.FontWeight.W_700,
                            color=self.p["text"],
                        ),
                        ui.Text(desc, size=12.5, color=self.p["sub"], width=560),
                    ],
                ),
            ],
        )

    def _architecture(self) -> ui.Control:
        steps = [
            (
                "引擎层 engine.py",
                "ctypes 直调 Everything 1.5 SDK DLL，串行锁 + 看门狗 + 索引变更监听。",
            ),
            (
                "数据层",
                "store 负责配置/书签 JSON，history 用 SQLModel/SQLite 记录运行次数。",
            ),
            (
                "控制层 controller",
                "搜索防抖、分页、选中、文件动作、窗口与快捷键按职责拆分。",
            ),
            ("界面层 ui", "cs-ui 声明式组件（底层 Flet）：f(state) 自动重绘，设计令牌统一视觉。"),
            (
                "系统集成",
                "pystray 托盘、pynput 全局热键、WH_MOUSE_LL 滚轮桥，全部守护线程运行。",
            ),
        ]
        return ui.Container(
            key="architecture",
            bgcolor=self.p["surface"],
            padding=ui.Padding(24, 56, 24, 56),
            content=ui.Column(
                spacing=24,
                horizontal_alignment=ui.CrossAxisAlignment.CENTER,
                controls=[
                    self._section_title(
                        "ARCHITECTURE", "分层架构", "清晰的单向依赖，便于维护与扩展"
                    ),
                    self._card(
                        ui.Column(
                            spacing=16,
                            controls=[
                                self._arch_step(i + 1, *s) for i, s in enumerate(steps)
                            ],
                        ),
                        pad=24,
                    ),
                ],
            ),
        )

    # ------------------------------------------------------------------ 快速开始
    def _quick_step(
        self, index: int, title: str, cmd: str | None, desc: str
    ) -> ui.Control:
        body = [
            ui.Row(
                spacing=10,
                controls=[
                    ui.Text(
                        f"{index}", size=14, weight=ui.FontWeight.W_800, color=_ACCENT
                    ),
                    ui.Text(
                        title, size=14, weight=ui.FontWeight.W_700, color=self.p["text"]
                    ),
                ],
            ),
            ui.Text(desc, size=12.5, color=self.p["sub"]),
        ]
        if cmd:
            body.append(
                ui.Container(
                    bgcolor=self.p["surface"],
                    border_radius=8,
                    padding=ui.Padding(12, 8, 8, 8),
                    border=ui.Border.all(1, self.p["border"]),
                    content=ui.Row(
                        controls=[
                            ui.Text(
                                cmd,
                                size=12.5,
                                expand=True,
                                font_family="Consolas",
                                color=self.p["text"],
                            ),
                            ui.IconButton(
                                ui.Icons.CONTENT_COPY,
                                icon_size=16,
                                tooltip="复制命令",
                                on_click=lambda e, c=cmd: self._copy(c),
                            ),
                        ],
                    ),
                )
            )
        return self._card(ui.Column(spacing=8, controls=body))

    def _copy(self, cmd: str) -> None:
        self.snack("命令已复制" if _copy_text(cmd) else "复制失败，请手动选择文本复制")

    def _quickstart(self) -> ui.Control:
        steps = [
            (
                1,
                "安装依赖",
                "pip install -r requirements.txt",
                "需要 Python 3.12+，并安装/运行 Everything 1.5（x64）。",
            ),
            (
                2,
                "启动应用",
                "python main.py",
                "桌面窗口启动；首次会自动检测 Everything 服务与索引状态。",
            ),
            (
                3,
                "唤起搜索",
                None,
                "默认 Alt+Space 全局唤起；在设置中可改为 ctrl+shift+f 等组合。",
            ),
            (
                4,
                "打包发布",
                "flet build windows",
                "产出独立 exe；assets 内放置字体与图标即可离线运行。",
            ),
        ]
        return ui.Container(
            key="quickstart",
            padding=ui.Padding(24, 56, 24, 56),
            content=ui.Column(
                spacing=20,
                horizontal_alignment=ui.CrossAxisAlignment.CENTER,
                controls=[
                    self._section_title("QUICK START", "快速开始", "四步跑起来"),
                    ui.Column(
                        width=720,
                        spacing=12,
                        controls=[self._quick_step(*s) for s in steps],
                    ),
                ],
            ),
        )

    # ------------------------------------------------------------------ 页脚
    def _footer(self) -> ui.Control:
        return ui.Container(
            bgcolor=self.p["surface"],
            padding=ui.Padding(24, 28, 24, 28),
            border=ui.Border(top=ui.BorderSide(1, self.p["border"])),
            content=ui.Column(
                horizontal_alignment=ui.CrossAxisAlignment.CENTER,
                spacing=6,
                controls=[
                    ui.Row(
                        alignment=ui.MainAxisAlignment.CENTER,
                        spacing=8,
                        controls=[
                            ui.Icon(ui.Icons.SPEED, color=_ACCENT, size=18),
                            ui.Text(
                                "CSearch",
                                size=14,
                                weight=ui.FontWeight.W_700,
                                color=self.p["text"],
                            ),
                        ],
                    ),
                    ui.Text(
                        "Everything 1.5 + cs-ui · 桌面极速文件搜索",
                        size=12,
                        color=self.p["hint"],
                    ),
                ],
            ),
        )


async def main(page: ui.Page) -> None:
    site = LandingSite(page)
    site.setup()
    site.render()


if __name__ == "__main__":
    ui.run(main)  # 默认桌面原生窗口；加 -w 可在浏览器打开
