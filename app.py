# -*- coding: utf-8 -*-
"""
CS-Search 官方介绍站点（单文件 · 纯 Flet 实现）

运行方式：
    flet run app.py

说明：
    - 仅依赖 flet 库，无任何外部资源 / 前端依赖
    - 声明式 UI：以控件树方式构建页面，按区域分块组织
    - 响应式：桌面端横向布局，移动端自动换行 / 折叠菜单
    - 交互：导航平滑滚动、滚动毛玻璃导航栏、卡片悬停上浮、
            亮暗主题切换（持久化）、首屏淡入动画
    - 适配目标版本：flet 0.86.x（API 以 ft.Colors / ft.Icons / ft.Alignment 等枚举与类为准）
"""

import asyncio
import flet as ft

# ======================================================================
# 一、常量配置区（关键参数集中提取，便于统一修改）
# ======================================================================

# 项目基础信息（依据 cs-search 真实项目填写）
PROJECT_NAME = "CSearch"
PROJECT_TAGLINE = "复刻 Everything 的 Windows 极速本地文件搜索 · Flet 声明式桌面应用"
SLOGAN = "毫秒级本地文件搜索，复刻 Everything 的极致体验"
SUB_SLOGAN = "Everything 1.5 + · 输入即搜 · 实时索引同步 · 系统托盘常驻"
VERSION_LABEL = "v2.0.0"

# 外链（TODO: 替换为真实地址；GitHub 仓库当前项目未公开，保留占位）
GITHUB_URL = "https://github.com/your-org/cs-search"
DOCS_URL = "https://www.voidtools.com/support/everything/searching/"   # Everything 官方搜索语法文档
EVERYTHING_URL = "https://www.voidtools.com/zh-cn/downloads/"           # 前置依赖：Everything 1.5+

# 主题持久化的存储键
THEME_STORAGE_KEY = "cs_search_theme"

# 响应式断点（窗口宽度小于该值视为移动端）
MOBILE_BREAKPOINT = 760

# 导航菜单项：(显示文本, 锚点 key)
NAV_ITEMS = [
    ("首页", "home"),
    ("特性", "features"),
    ("架构", "architecture"),
    ("快速开始", "quickstart"),
    ("关于", "about"),
]

# 极简起步命令（单行复制内容）
INSTALL_CMD = "pip install -e ."

# 快速开始三行步骤
QUICKSTART_STEPS = [
    ("安装依赖", "pip install -e .（需 Python 3.12+），依赖 flet / everytools / pystray 等。"),
    ("连接 Everything", "确保 Everything 1.5+ 已运行；未运行会给出友好提示与一键启动引导。"),
    ("开始搜索", "输入即搜（防抖 100ms），原生语法 + 多维过滤，右键/快捷键操作文件。"),
]

# ======================================================================
# 二、对齐辅助（flet 0.86 使用 ft.Alignment(水平, 垂直)，取值 -1~1）
# ======================================================================
ALIGN_CENTER = ft.Alignment(0, 0)
ALIGN_TL = ft.Alignment(-1, -1)   # 左上
ALIGN_TR = ft.Alignment(1, -1)    # 右上
ALIGN_BR = ft.Alignment(1, 1)     # 右下
ALIGN_BL = ft.Alignment(-1, 1)     # 左下

# ======================================================================
# 三、内边距 / 外边距辅助（flet 0.86 用 ft.Padding / ft.Margin 显式构造）
# ======================================================================
def pad_symmetric(h: int = 0, v: int = 0) -> ft.Padding:
    return ft.Padding(left=h, right=h, top=v, bottom=v)

def pad_all(x: int) -> ft.Padding:
    return ft.Padding(left=x, right=x, top=x, bottom=x)

def pad(l: int = 0, t: int = 0, r: int = 0, b: int = 0) -> ft.Padding:
    return ft.Padding(left=l, right=r, top=t, bottom=b)

def margin_symmetric(h: int = 0, v: int = 0) -> ft.Margin:
    return ft.Margin(left=h, right=h, top=v, bottom=v)

def margin_all(x: int) -> ft.Margin:
    return ft.Margin(left=x, right=x, top=x, bottom=x)

def margin(l: int = 0, t: int = 0, r: int = 0, b: int = 0) -> ft.Margin:
    return ft.Margin(left=l, right=r, top=t, bottom=b)

def border_all(color) -> ft.Border:
    """四边等宽边框（flet 0.86 的 Border 不支持 all= 关键字）。"""
    s = ft.BorderSide(1, color)
    return ft.Border(left=s, right=s, top=s, bottom=s)

# 滚动锚点 key 构造器（scroll_to 依据 ScrollKey 定位目标控件）
def SEC(name: str) -> ft.ScrollKey:
    return ft.ScrollKey(name)

# ======================================================================
# 四、调色板（蓝灰色系 · 亮 / 暗 双主题）
# ======================================================================
# 统一使用 ft.Colors 枚举；透明色通过 ft.Colors.with_opacity 生成（返回十六进制字符串）。

PALETTE = {
    "light": {
        "bg": ft.Colors.BLUE_GREY_50,
        "surface": ft.Colors.WHITE,
        "surface_2": ft.Colors.BLUE_GREY_100,
        "primary": ft.Colors.BLUE_GREY_700,
        "primary_light": ft.Colors.BLUE_GREY_500,
        "text": ft.Colors.BLUE_GREY_900,
        "text_muted": ft.Colors.BLUE_GREY_500,
        "border": ft.Colors.BLUE_GREY_200,
        # 首屏渐变（左上 -> 右下）
        "hero_grad": [ft.Colors.BLUE_GREY_100, ft.Colors.BLUE_GREY_50, ft.Colors.WHITE],
        "blob": ft.Colors.BLUE_GREY_300,          # 装饰光晕基色
        "nav_glass": ft.Colors.with_opacity(0.72, ft.Colors.WHITE),  # 滚动后毛玻璃
        "code_bg": ft.Colors.BLUE_GREY_900,
        "code_text": ft.Colors.BLUE_GREY_50,
    },
    "dark": {
        "bg": ft.Colors.BLUE_GREY_900,
        "surface": ft.Colors.BLUE_GREY_800,
        "surface_2": ft.Colors.BLUE_GREY_700,
        "primary": ft.Colors.BLUE_GREY_300,
        "primary_light": ft.Colors.BLUE_GREY_400,
        "text": ft.Colors.BLUE_GREY_50,
        "text_muted": ft.Colors.BLUE_GREY_400,
        "border": ft.Colors.BLUE_GREY_700,
        "hero_grad": [ft.Colors.BLUE_GREY_800, ft.Colors.BLUE_GREY_900, ft.Colors.BLACK],
        "blob": ft.Colors.BLUE_GREY_600,
        "nav_glass": ft.Colors.with_opacity(0.72, ft.Colors.BLUE_GREY_800),
        "code_bg": ft.Colors.BLACK,
        "code_text": ft.Colors.BLUE_GREY_100,
    },
}

# 卡片阴影（亮暗主题共用，使用黑色半透明，简洁通用）
SHADOW_REST = ft.BoxShadow(
    blur_radius=8, spread_radius=0,
    color=ft.Colors.with_opacity(0.10, ft.Colors.BLACK),
    offset=ft.Offset(0, 2),
)
SHADOW_HOVER = ft.BoxShadow(
    blur_radius=22, spread_radius=0,
    color=ft.Colors.with_opacity(0.20, ft.Colors.BLACK),
    offset=ft.Offset(0, 10),
)

# 统一的微动效曲线
EASE = ft.AnimationCurve.EASE_OUT


# ======================================================================
# 五、主程序
# ======================================================================

def main(page: ft.Page):
    # ----- 页面基础设置 -----
    page.title = f"{PROJECT_NAME} · 官方站点"
    page.padding = 0
    page.spacing = 0
    page.theme_mode = load_theme(page)

    # 当前主题取色助手
    def P(key):
        return PALETTE[page.theme_mode][key]

    # 内容区最大宽度：桌面端居中限宽，窄屏自动铺满（随窗口实时计算）
    def content_max_w():
        w = page.width or 1080
        return min(1080, max(280, w - 48))  # 两侧各留 24 内边距

    page.bgcolor = P("bg")

    # 跨渲染共享的状态 / 引用
    state = {"menu_open": False}
    scroll_col = {}        # 保存内部滚动列，用于 scroll_to
    nav_refs = {}          # 保存导航子元素，用于窗口尺寸变化时更新可见性
    section_boxes = []     # 保存所有“限宽内容容器”，用于窗口缩放时同步重算宽度
    hero_shown = {"v": False}  # 首屏淡入是否已完成（仅首次）

    # 轻量 Toast（兼容新旧 flet 的 SnackBar 调用方式）
    def toast(msg: str):
        sb = ft.SnackBar(content=ft.Text(msg), action="好的")
        try:
            page.open(sb)
        except Exception:
            try:
                page.overlay.append(sb)
                sb.open = True
                page.update()
            except Exception:
                pass

    # 平滑滚动到指定锚点
    # 注意：scroll_to 是 async 方法，需通过 run_task 在页面事件循环中 await 执行
    def go(key: str):
        async def _scroll():
            try:
                await scroll_col["col"].scroll_to(
                    scroll_key=SEC(key), duration=550, curve=ft.AnimationCurve.EASE_IN_OUT
                )
            except Exception:
                pass

        try:
            page.run_task(_scroll)
        except Exception:
            pass

    # ==================================================================
    # 六、各区域构建函数（均嵌套在 main 内，便于共享 page / P / go）
    # ==================================================================

    # ---------------- 6.1 顶部导航栏 ----------------
    def build_nav():
        # Logo
        logo = ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=34, height=34, border_radius=9,
                    gradient=ft.LinearGradient(
                        begin=ALIGN_TL, end=ALIGN_BR,
                        colors=[ft.Colors.BLUE_GREY_600, ft.Colors.BLUE_GREY_900],
                    ),
                    content=ft.Icon(ft.Icons.HUB_OUTLINED, color=ft.Colors.WHITE, size=20),
                    alignment=ALIGN_CENTER,
                ),
                ft.Text(PROJECT_NAME, size=19, weight=ft.FontWeight.BOLD, color=P("text")),
            ],
        )

        # 桌面端：内联导航链接
        links = ft.Row(
            spacing=6,
            visible=page.width is None or page.width >= MOBILE_BREAKPOINT,
            controls=[nav_link(label, key) for label, key in NAV_ITEMS],
        )

        # 主题切换按钮
        theme_btn = ft.IconButton(
            icon=ft.Icons.DARK_MODE if page.theme_mode == "light" else ft.Icons.LIGHT_MODE,
            tooltip="切换亮 / 暗主题",
            on_click=lambda e: toggle_theme(),
            icon_color=P("text"),
        )

        # 移动端：汉堡菜单按钮
        hamburger = ft.IconButton(
            icon=ft.Icons.MENU,
            tooltip="菜单",
            icon_color=P("text"),
            visible=page.width is not None and page.width < MOBILE_BREAKPOINT,
            on_click=lambda e: toggle_menu(),
        )

        # 导航栏主体（毛玻璃在滚动时启用）
        bar = ft.Container(
            padding=pad_symmetric(24, 10),
            bgcolor=ft.Colors.TRANSPARENT,
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[logo, links, ft.Row(spacing=4, controls=[theme_btn, hamburger])],
            ),
            animate=ft.Animation(250, EASE),
        )

        # 移动端下拉菜单（默认隐藏）
        mobile_menu = ft.Container(
            visible=state["menu_open"],
            bgcolor=P("surface"),
            border=ft.Border(bottom=ft.BorderSide(1, P("border"))),
            padding=pad_symmetric(0, 6),
            content=ft.Column(
                controls=[nav_link(label, key, on_tap=toggle_menu) for label, key in NAV_ITEMS]
            ),
        )

        # 记录子元素引用，供窗口尺寸变化时更新可见性
        nav_refs["links"] = links
        nav_refs["hamburger"] = hamburger
        nav_refs["mobile_menu"] = mobile_menu
        nav_refs["bar"] = bar

        return ft.Column(spacing=0, controls=[bar, mobile_menu])

    def nav_link(label, key, on_tap=None):
        # 文本型导航链接（hover 有底色过渡）
        def on_click(e):
            go(key)
            if on_tap:
                on_tap()
        return ft.TextButton(
            content=ft.Text(label, color=P("text_muted")),
            on_click=on_click,
            style=ft.ButtonStyle(
                overlay_color=ft.Colors.with_opacity(0.08, P("primary")),
                padding=pad_symmetric(14, 8),
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
        )

    def toggle_menu():
        state["menu_open"] = not state["menu_open"]
        render()

    # ---------------- 6.2 首屏 Hero ----------------
    def build_hero(animate: bool):
        # 装饰光晕（两个柔和的圆形渐变）
        blob1 = ft.Container(
            width=340, height=340, border_radius=9999,
            margin=margin(t=-130, r=-130),
            gradient=ft.RadialGradient(
                center=ALIGN_CENTER, radius=1.0,
                colors=[ft.Colors.with_opacity(0.45, P("blob")),
                        ft.Colors.with_opacity(0.0, P("blob"))],
                stops=[0, 1],
            ),
        )
        blob2 = ft.Container(
            width=280, height=280, border_radius=9999,
            margin=margin(b=-110, l=-110),
            gradient=ft.RadialGradient(
                center=ALIGN_CENTER, radius=1.0,
                colors=[ft.Colors.with_opacity(0.35, P("primary_light")),
                        ft.Colors.with_opacity(0.0, P("primary_light"))],
                stops=[0, 1],
            ),
        )

        # 标题区
        content = ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=18,
            controls=[
                ft.Container(
                    padding=pad_symmetric(14, 6),
                    border_radius=999,
                    bgcolor=ft.Colors.with_opacity(0.12, P("primary")),
                    content=ft.Text(f"{VERSION_LABEL} 现已发布", size=12, color=P("primary"), weight=ft.FontWeight.W_600),
                ),
                ft.Text(PROJECT_NAME, size=56, weight=ft.FontWeight.BOLD, color=P("text"),
                        text_align=ft.TextAlign.CENTER),
                ft.Text(SLOGAN, size=22, weight=ft.FontWeight.W_500, color=P("primary"),
                        text_align=ft.TextAlign.CENTER),
                ft.Text(SUB_SLOGAN, size=15, color=P("text_muted"),
                        text_align=ft.TextAlign.CENTER),
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=14,
                    controls=[
                        ft.FilledButton(
                            content=ft.Text("立即开始"), icon=ft.Icons.ROCKET_LAUNCH,
                            on_click=lambda e: go("quickstart"),
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                        ),
                        ft.OutlinedButton(
                            content=ft.Text("Everything 1.5 下载"), icon=ft.Icons.DOWNLOAD,
                            url=EVERYTHING_URL,
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                        ),
                    ],
                ),
            ],
        )

        hero = ft.Container(
            key=SEC("home"),
            alignment=ALIGN_CENTER,   # 占满整行宽度，渐变满铺
            padding=pad_symmetric(24, 90),
            gradient=ft.LinearGradient(
                begin=ALIGN_TL, end=ALIGN_BR,
                colors=P("hero_grad"),
            ),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Stack(
                alignment=ALIGN_CENTER,
                controls=[blob1, blob2, content],
            ),
            opacity=0 if animate else 1,
            animate_opacity=ft.Animation(900, EASE),
        )
        return hero

    # ---------------- 6.3 核心特性区 ----------------
    def build_features():
        cards = [
            ("极速搜索", ft.Icons.FLASH_ON,
             "输入防抖 100ms，Everything 原生语法（关键词 / 通配符 / 正则 / ext: / content:）；"
             "结果懒加载，首批 200 条增量加载，29 万结果首屏仅 15~80ms。"),
            ("实时索引同步", ft.Icons.SYNC,
             "5s 轻量签名轮询静默刷新结果并保留选中状态；放入官方 1.5 SDK DLL 后自动升级为"
             "Everything_SetNotifyWindow 事件驱动通知。"),
            ("全量文件操作", ft.Icons.FOLDER_OPEN,
             "右键菜单 + 快捷键，多选批量打开 / 定位 / 复制路径 / 复制文件名 / "
             "删除，默认移入回收站，无需确认，删除后自动选中下一项。"),
            ("多维过滤器", ft.Icons.FILTER_ALT,
             "分类（文件夹 / 文档 / 图片 / 视频 / 音频 / 压缩包 / 可执行）+ 修改时间 + 大小区间，"
             "与关键词叠加生效。"),
            ("书签系统", ft.Icons.BOOKMARK,
             "保存「关键词 + 过滤器」组合，卡片式展示，一键应用，支持重命名 / 删除，JSON 持久化。"),
            ("全局热键与托盘", ft.Icons.KEYBOARD,
             "默认 Alt+Space 唤起 / 隐藏，关闭窗口最小化托盘（pystray + pynput 守护线程）；"
             "快捷键导航齐全。"),
        ]

        def make_card(title, icon, desc):
            inner = ft.Container(
                padding=24,
                border_radius=16,
                bgcolor=P("surface"),
                border=border_all(P("border")),
                shadow=SHADOW_REST,
                animate=ft.Animation(220, EASE),
                on_hover=on_card_hover,
                content=ft.Column(
                    spacing=12,
                    controls=[
                        ft.Container(
                            width=46, height=46, border_radius=12,
                            bgcolor=ft.Colors.with_opacity(0.12, P("primary")),
                            content=ft.Icon(icon, color=P("primary"), size=24),
                            alignment=ALIGN_CENTER,
                        ),
                        ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=P("text")),
                        ft.Text(desc, size=13.5, color=P("text_muted"), height=1.5),
                    ],
                ),
            )
            # 响应式列宽：大屏 3 列，中屏 3 列，小屏 2 列，超小屏 1 列
            return ft.Container(
                col={"xs": 12, "sm": 6, "md": 4, "lg": 4},
                content=inner,
            )

        grid = ft.ResponsiveRow(
            spacing=18, run_spacing=18,
            controls=[make_card(t, i, d) for t, i, d in cards],
        )

        return section(
            key="features",
            title="核心特性",
            subtitle="复刻 Everything 的极速本地文件搜索体验",
            content=grid,
        )

    def on_card_hover(e):
        box = e.control
        if e.data == "true":
            box.shadow = SHADOW_HOVER
            box.margin = margin(t=-6, b=6)
        else:
            box.shadow = SHADOW_REST
            box.margin = margin_symmetric(0, 0)
        box.update()

    # ---------------- 6.4 架构 / 工作原理图 ----------------
    def build_architecture():
        # 对应真实模块与数据流：UI 输入 → 业务编排 → Everything 引擎 → 状态层 → 声明式渲染
        stages = [
            ("搜索输入", ft.Icons.SEARCH, "搜索框 + 键盘事件（↓/↑/Enter/Esc），防抖 100ms"),
            ("业务编排", ft.Icons.HUB_OUTLINED, "logic.py：解析查询、分页、事件分发"),
            ("Everything 引擎", ft.Icons.STORAGE, "engine.py：SDK 分页查询 / 排序 / 索引轮询"),
            ("状态层", ft.Icons.INSIGHTS, "state.py：@ft.observable 数据类 + 服务单例"),
            ("声明式 UI", ft.Icons.VISIBILITY, "ui/ 组件：UI = f(state) 自动重绘"),
        ]

        flow = []
        for idx, (title, icon, sub) in enumerate(stages):
            node = ft.Container(
                width=150,
                padding=16,
                border_radius=14,
                bgcolor=P("surface"),
                border=border_all(P("border")),
                shadow=SHADOW_REST,
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                    controls=[
                        ft.Container(
                            width=42, height=42, border_radius=11,
                            bgcolor=ft.Colors.with_opacity(0.12, P("primary")),
                            content=ft.Icon(icon, color=P("primary"), size=22),
                            alignment=ALIGN_CENTER,
                        ),
                        ft.Text(title, size=14, weight=ft.FontWeight.BOLD, color=P("text")),
                        ft.Text(sub, size=11, color=P("text_muted"), text_align=ft.TextAlign.CENTER),
                    ],
                ),
            )
            flow.append(node)
            if idx < len(stages) - 1:
                flow.append(
                    ft.Container(
                        content=ft.Icon(ft.Icons.ARROW_FORWARD, color=P("primary_light"), size=26),
                        margin=margin_symmetric(4, 0),
                    )
                )

        diagram = ft.Container(
            padding=28,
            border_radius=18,
            bgcolor=P("surface_2"),
            content=ft.Row(
                wrap=True,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=8, run_spacing=14,
                controls=flow,
            ),
        )

        return section(
            key="architecture",
            title="架构与工作原理",
            subtitle="声明式架构：UI = f(state)，状态变更自动驱动重绘",
            content=diagram,
        )

    # ---------------- 6.5 快速开始区 ----------------
    def build_quickstart():
        code_text = (
            "# 1. 安装（开发模式，需 Python 3.12+）\n"
            "cd D:\\projects\\cs-search\n"
            "pip install -e .\n\n"
            "# 2. 前置：确保 Everything 1.5+ 已运行\n"
            "#    未运行会在界面给出友好提示与一键启动引导\n\n"
            "# 3. 启动 CSearch\n"
            "python main.py"
        )

        # 代码块（带一键复制）
        code_block = ft.Container(
            padding=20,
            border_radius=14,
            bgcolor=P("code_bg"),
            border=border_all(P("border")),
            content=ft.Column(
                spacing=0,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.CONTENT_COPY,
                                icon_color=P("code_text"),
                                tooltip="复制代码",
                                on_click=lambda e: copy_text(code_text),
                            )
                        ],
                    ),
                    ft.Text(
                        code_text,
                        size=13.5,
                        color=P("code_text"),
                        font_family="Consolas, Menlo, monospace",
                        selectable=True,
                        height=1.6,
                    ),
                ],
            ),
        )

        # 三行起步步骤
        steps = ft.Column(
            spacing=14,
            controls=[
                ft.Row(
                    spacing=14, vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Container(
                            width=28, height=28, border_radius=999,
                            bgcolor=P("primary"),
                            content=ft.Text(str(i + 1), color=ft.Colors.WHITE,
                                            size=13, weight=ft.FontWeight.BOLD),
                            alignment=ALIGN_CENTER,
                        ),
                        ft.Column(
                            spacing=2, expand=True,
                            controls=[
                                ft.Text(title, size=15, weight=ft.FontWeight.BOLD, color=P("text")),
                                ft.Text(desc, size=13, color=P("text_muted")),
                            ],
                        ),
                    ],
                )
                for i, (title, desc) in enumerate(QUICKSTART_STEPS)
            ],
        )

        body = ft.ResponsiveRow(
            spacing=24, run_spacing=24,
            controls=[
                ft.Container(col={"xs": 12, "lg": 7}, content=code_block),
                ft.Container(col={"xs": 12, "lg": 5}, content=steps,
                             padding=pad(t=6)),
            ],
        )

        # 安装命令单行展示（也支持复制）
        install_row = ft.Container(
            margin=margin(t=18),
            padding=pad_symmetric(18, 14),
            border_radius=12,
            bgcolor=P("surface"),
            border=border_all(P("border")),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Row(
                        spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.TERMINAL, size=18, color=P("primary")),
                            ft.Text(INSTALL_CMD, size=14, font_family="Consolas, monospace",
                                    color=P("text"), selectable=True),
                        ],
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CONTENT_COPY, tooltip="复制安装命令",
                        icon_color=P("primary"),
                        on_click=lambda e: copy_text(INSTALL_CMD),
                    ),
                ],
            ),
        )

        return section(
            key="quickstart",
            title="快速开始",
            subtitle="三步启动，连接 Everything 即刻搜索",
            content=ft.Column(controls=[body, install_row]),
        )

    # ---------------- 6.6 底部页脚 ----------------
    def build_footer():
        socials = [
            (ft.Icons.CODE, "GitHub 源码", GITHUB_URL),
            (ft.Icons.DESCRIPTION, "搜索语法", DOCS_URL),
            (ft.Icons.DOWNLOAD, "Everything 1.5", EVERYTHING_URL),
        ]
        social_row = ft.Row(
            spacing=10,
            controls=[
                ft.IconButton(icon=i, tooltip=name, url=url, icon_color=P("text_muted"))
                for i, name, url in socials
            ],
        )

        footer = ft.Container(
            key=SEC("about"),
            width=content_max_w(),   # 与区块一致地限宽并居中
            padding=pad_symmetric(24, 36),
            margin=margin(t=20),
            bgcolor=P("surface"),
            border=ft.Border(top=ft.BorderSide(1, P("border"))),
            content=ft.ResponsiveRow(
                spacing=20, run_spacing=20,
                controls=[
                    ft.Container(
                        col={"xs": 12, "md": 6},
                        content=ft.Column(
                            spacing=8,
                            controls=[
                                ft.Text(PROJECT_NAME, size=16, weight=ft.FontWeight.BOLD,
                                        color=P("text")),
                                ft.Text(PROJECT_TAGLINE, size=13, color=P("text_muted")),
                            ],
                        ),
                    ),
                    ft.Container(
                        col={"xs": 12, "md": 6},
                        content=ft.Row(
                            alignment=ft.MainAxisAlignment.END,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=8,
                            controls=[social_row],
                        ),
                    ),
                ],
            ),
        )
        section_boxes.append(footer)

        copyright = ft.Container(
            padding=pad_symmetric(24, 14),
            bgcolor=P("bg"),
            content=ft.Text(
                f"© 2026 {PROJECT_NAME}. 以 MIT 协议开源发布。",
                size=12, color=P("text_muted"), text_align=ft.TextAlign.CENTER,
            ),
        )

        return ft.Column(
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[footer, copyright],
        )

    # ---------------- 公共：区块容器（标题 + 内容 + 锚点） ----------------
    def section(key, title, subtitle, content):
        # 限宽内容容器：宽度随窗口实时计算，并登记以便缩放时同步更新
        content_box = ft.Container(
            width=content_max_w(),
            content=content,
        )
        section_boxes.append(content_box)

        return ft.Container(
            key=SEC(key),
            padding=pad_symmetric(24, 64),
            content=ft.Column(
                spacing=28,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                        controls=[
                            ft.Text(title, size=30, weight=ft.FontWeight.BOLD, color=P("text")),
                            ft.Text(subtitle, size=15, color=P("text_muted")),
                        ],
                    ),
                    content_box,
                ],
            ),
        )

    # ---------------- 复制 / 主题相关 ----------------
    def copy_text(text: str):
        try:
            page.clipboard.set(text)
            toast("已复制到剪贴板")
        except Exception:
            toast("复制失败，请手动选择")

    def toggle_theme():
        page.theme_mode = "dark" if page.theme_mode == "light" else "light"
        save_theme(page)
        render()

    # ==================================================================
    # 七、渲染与事件绑定
    # ==================================================================

    def on_scroll(e):
        """滚动时切换导航栏毛玻璃效果。"""
        bar = nav_refs.get("bar")
        if bar is None:
            return
        offset = getattr(e, "pixel", None)
        if offset is None:
            offset = getattr(e, "scroll_offset", 0) or 0
        if offset > 24:
            bar.bgcolor = P("nav_glass")
            bar.border = ft.Border(bottom=ft.BorderSide(1, P("border")))
        else:
            bar.bgcolor = ft.Colors.TRANSPARENT
            bar.border = None
        bar.update()

    def on_resize(e):
        """窗口尺寸变化时：切换导航菜单可见性，并同步所有限宽容器的宽度。"""
        is_mobile = (page.width or 1200) < MOBILE_BREAKPOINT
        if "links" in nav_refs:
            nav_refs["links"].visible = not is_mobile
        if "hamburger" in nav_refs:
            nav_refs["hamburger"].visible = is_mobile
        if "mobile_menu" in nav_refs:
            # 离开移动端时自动收起下拉菜单
            nav_refs["mobile_menu"].visible = is_mobile and state["menu_open"]

        # 关键：限宽内容容器随窗口重算宽度，避免缩放后行未占满 / 内容偏左
        w = content_max_w()
        for box in section_boxes:
            box.width = w

        page.update()

    # 组装整页
    def render():
        page.controls.clear()
        page.bgcolor = P("bg")
        section_boxes.clear()   # 重新登记本轮渲染的限宽容器

        nav = build_nav()
        body = ft.Column(
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            spacing=0,
            on_scroll=on_scroll,
            controls=[
                build_hero(animate=not hero_shown["v"]),
                build_features(),
                build_architecture(),
                build_quickstart(),
                build_footer(),
            ],
        )
        scroll_col["col"] = body

        page.add(ft.Column(expand=True, spacing=0, controls=[nav, body]))
        page.update()

        # 首屏淡入：先以 opacity=0 渲染，下一帧置为 1 触发过渡动画
        if not hero_shown["v"]:
            hero_shown["v"] = True
            hero = body.controls[0]
            try:
                # run_task 接收「协程函数 + 参数」，不能传入已创建的协程对象
                page.run_task(fade_in, hero)
            except Exception:
                hero.opacity = 1
                page.update()

    async def fade_in(hero):
        await asyncio.sleep(0.08)
        hero.opacity = 1
        try:
            hero.update()
        except Exception:
            page.update()

    # 绑定窗口尺寸变化
    page.on_resize = on_resize

    # 首次渲染
    render()


# ======================================================================
# 八、主题持久化（client_storage，失败则回退到默认亮色）
# ======================================================================

def load_theme(page: ft.Page) -> str:
    try:
        saved = page.client_storage.get(THEME_STORAGE_KEY)
        if saved in ("light", "dark"):
            return saved
    except Exception:
        pass
    return "light"


def save_theme(page: ft.Page):
    try:
        page.client_storage.set(THEME_STORAGE_KEY, page.theme_mode)
    except Exception:
        pass


# ======================================================================
# 九、入口
# ======================================================================

if __name__ == "__main__":
    ft.run(main)
