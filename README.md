# CSearch — Everything 1.5 极速文件搜索（Flet 0.86.5 声明式）

在 Windows 10/11 上复刻 Everything 的本地文件搜索体验：毫秒级回显、Everything 原生搜索语法、
实时索引同步、系统托盘常驻、全局热键唤起。**完全基于 Everything 1.5 + Python 3.12 + Flet 0.86.5。**

## 快速开始

```powershell
cd D:\projects\cs-search
C:\Softwares\Python-V3.12.10.x64\python.exe -m pip install -e .   # 或 pip install -e .
C:\Softwares\Python-V3.12.10.x64\python.exe main.py               # 或 python main.py
```

前置条件：已安装并运行 [Everything 1.5+](https://www.voidtools.com/zh-cn/downloads/)。
启动时自动检测 Everything 服务，未运行时界面给出友好提示与一键启动引导。

## 界面布局（单列）

```
┌──────────────────────────────────────────────────────────────┐
│ [搜索框................] [分类▾] [时间▾] [大小▾] [☆][⟳][⚙]    │
├──────────────────────────────────────────────────────────────┤
│ 搜索框无内容 → 书签卡片区（点击一键应用，卡片可重命名/删除）      │
│ 输入关键词   → 结果列表（名称|路径|大小|修改时间，右键菜单操作）   │
├──────────────────────────────────────────────────────────────┤
│ 状态栏：结果数 / 耗时 · 索引状态 / 版本号                        │
└──────────────────────────────────────────────────────────────┘
```

- 搜索行：搜索框 + 分类/修改时间/文件大小三联动筛选（与关键词叠加生效）+ 保存书签/刷新/热键设置。
- 搜索框无内容时**不显示搜索结果**，结果区展示书签面板；输入即搜（防抖 300ms）。
- 书签卡片显示名称与条件摘要，点击应用、菜单重命名/删除。

## 功能

1. 极速搜索：输入防抖 300ms，Everything 原生语法（关键词 / 通配符 / 正则 / `ext:` / `content:`），
   结果懒加载（首批 200 条，滚动触底增量加载），表头点击切换四列排序。
2. 实时索引同步：5s 轻量签名轮询静默刷新结果，保留选中状态；放入官方 1.5 SDK DLL 到
   `vendor/` 后自动升级为 `Everything_SetNotifyWindow` 事件驱动通知。
3. 文件操作：右键菜单 + 快捷键，多选批量（打开 / 定位 / 复制路径 / 复制文件名 /
   回收站删除 / 永久删除，删除前二次确认）。
4. 多维过滤：分类（全部/文件夹/文档/图片/视频/音频/压缩包/可执行文件）、修改时间范围、大小区间。
5. 书签：保存"关键词+过滤器"组合，卡片式展示，一键应用，重命名/删除，JSON 持久化。
6. 全局热键 + 系统托盘：默认 `Alt+Space`（可自定义），关闭窗口最小化托盘
   （纯 ctypes Shell_NotifyIconW，零额外依赖）。
7. 键盘导航：`↓` 搜索框→列表，`↑/↓` 移动选中，`Enter` 打开，`Esc` 清空，
   `F5` 刷新，`Ctrl+D` 复制路径，`Ctrl+E` 定位，`Ctrl+A` 全选。
8. 窗口状态记忆：自动保存/恢复尺寸位置。

## 架构（v2 重构）

```
main.py                  入口：窗口配置 + 事件注册 + 渲染
csearch/
├── types.py             类型与常量（ResultItem / Bookmark / 排序常量 / 过滤器选项）
├── engine.py            Everything SDK 封装（分页查询 / 排序 / 看门狗 / 索引监听）
├── ops.py               文件操作（打开 / 定位 / 复制 / 删除 / 启动 Everything）
├── store.py             配置与书签 JSON 持久化（函数式）
├── services.py          事件桥 + 全局热键（pynput）+ 系统托盘（ctypes）
├── logic.py             业务编排（搜索 / 动作 / 书签 / 设置 / 事件分发）
├── state.py             应用状态（@ft.observable 数据类）+ 服务单例
└── ui/                  声明式组件：app / searchbar / bookmarks / results / statusbar / dialogs / icons
```

设计要点：

- 声明式范式：`UI = f(state)`，组件仅用 `use_state/use_effect/use_memo/use_dialog`，
  状态变更自动驱动重绘，无命令式控件操作。
- 异步铁律：所有 SDK/系统同步调用经 `asyncio.to_thread` 入线程池 + `threading.Lock` 串行化，
  事件循环零阻塞。
- Python 3.12 原生语法：`match-case`（键盘/窗口/桥事件分发）、`int | None` 联合类型、
  dataclass 等，无任何低版本兼容逻辑。
- 分页查询：`SetMax/SetOffset` 限制单次 IPC 传输量，`GetTotResults` 一次取总数，
  实测 29 万结果首屏 15~80ms。
- 排序常量：顺序式（名称 1/2、路径 3/4、大小 5/6、修改时间 13/14），1.5 服务器实测。
- 查询看门狗（5s）：`content:` 未启用内容索引时触发实时扫描，超时安全中止
  （不触碰 DLL 避免死锁，卡死线程自然结束后自动恢复）。
- 分类用 Everything 原生函数（`folder:`/`doc:`/`pic:`/`video:`/`audio:`/`exe:`），
  压缩包用 `ext:` 扩展名列表（`archive:` 函数在部分 1.5 配置下无效）。

## 数据

- 配置/书签：`%APPDATA%/CSearch/config.json` + `bookmarks.json`
- 退出：托盘菜单"退出程序"；关闭窗口仅最小化托盘

## 已知限制

- `content:` 需 Everything 启用内容索引（Tools > Options > Content），未启用时较慢并触发超时提示。
- 索引变更通知默认 5s 轮询；放置官方 1.5 SDK DLL 到 `vendor/` 后自动升级为事件驱动。
- 永久删除不可恢复；回收站模式走 send2trash。
