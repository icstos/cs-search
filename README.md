# CSearch — Everything 风格极速文件搜索（Flet + everytools）

在 Windows 10/11 上复刻 Everything 的本地文件搜索体验：毫秒级回显、Everything 原生搜索语法、
实时索引同步、系统托盘常驻、全局热键唤起。

## 快速开始

```powershell
cd D:\projects\cs-search
pip install -e .          # 安装依赖（flet / everytools / pynput / pyperclip / Send2Trash）
python main.py            # 启动
```

前置条件：本机已安装并运行 [Everything](https://www.voidtools.com/zh-cn/downloads/)（1.5+ 完整支持；
1.4 可用除 `doc:`/`pic:` 等 1.5 分类函数外的全部功能）。程序启动时会自动检测 Everything 服务，
未运行时在界面给出友好提示与一键启动引导。

## 功能总览

1. 极速搜索：输入防抖 300ms，Everything 原生语法（关键词 / 通配符 / 正则 / `ext:` / `content:` 等），
   结果懒加载（首批 200 条，滚动触底增量加载），表头点击切换排序。
2. 实时索引同步：通过 SDK 索引变更通知（Everything_SetNotifyWindow）静默刷新结果，
   保留当前选中状态；通知不可用时自动降级为 5s 签名轮询。
3. 文件操作：右键菜单 + 快捷键，支持多选批量（打开 / 定位 / 复制路径 / 复制文件名 /
   回收站删除 / 永久删除，删除前二次确认）。
4. 多维过滤：分类（全部/文件夹/文档/图片/视频/音频/压缩包/可执行文件）、修改时间范围、文件大小区间。
5. 书签：保存"关键词+过滤器"组合，一键应用，支持重命名/删除，JSON 持久化。
6. 全局热键 + 系统托盘：默认 `Alt+Space` 唤起/隐藏（可在设置中自定义）；
   关闭窗口最小化到托盘，托盘右键菜单可显示主窗口/退出。
7. 键盘导航：`↓` 搜索框→列表，`↑/↓` 移动选中，`Enter` 打开，`Esc` 清空搜索框，
   `F5` 刷新，`Ctrl+D` 复制路径，`Ctrl+E` 打开所在位置。
8. 窗口状态记忆：自动保存/恢复窗口尺寸与位置。

## 架构

```
main.py                  入口：窗口初始化、事件注册、渲染 App
csearch/
├── config.py            配置读写（窗口几何/热键，JSON 持久化，%APPDATA%/CSearch）
├── state.py             全局状态（@ft.observable dataclass）+ 服务单例 + 事件桥
├── search_engine.py     搜索内核：everytools DLL 装载 + 官方 SDK 常量适配 + 分页读取 + 索引监听
├── file_ops.py          文件操作（os.startfile / explorer /select / pyperclip / send2trash）
├── bookmarks.py         书签 CRUD（JSON 持久化）
├── hotkey_tray.py       全局热键（pynput）+ 系统托盘（ctypes Shell_NotifyIcon，零额外依赖）
├── controller.py        业务编排：防抖搜索、懒加载、静默刷新、菜单动作、对话框逻辑
├── icons.py             文件类型 → 图标/颜色 映射
└── ui/                  声明式组件：search_bar / sidebar / result_list / status_bar / dialogs / app
```

## 关键设计说明

- 声明式 UI：`UI = f(state)`，组件内仅用 `use_state`/`use_effect`/`use_dialog`/`use_memo`，
  无任何 `page.add()` / 手动 `update()` 改控件写法。
- 异步铁律：所有 everytools SDK 同步调用一律经 `asyncio.to_thread` 放入线程池执行，
  并加全局互斥锁串行化（SDK 为进程级单查询状态），Flet 事件循环零阻塞。
- SDK 适配：everytools 的 `SortType` 枚举值与官方 SDK 不一致（1=名称升序、2=路径升序…），
  引擎层直接使用官方 SDK 排序常量（升序为正、降序为负），保证"名称/路径/大小/修改时间"排序精确；
  `Everything_GetResultFullPathNameW` 在 everytools 中签名错误，引擎层已重新声明正确 ctypes 签名。
- 内容搜索 `content:` 直接透传 Everything 原生语法（需在 Everything 中启用内容索引）。
- 托盘用纯 ctypes 实现 `Shell_NotifyIconW`，无需 pystray/Pillow 额外依赖；
  托盘线程同时承载 Everything 索引变更通知窗口（WM_APP 消息 → 事件桥 → UI 静默刷新）。

## 配置与数据

- 配置/书签：`%APPDATA%/CSearch/config.json`（窗口几何、热键、启动隐藏）+ `bookmarks.json`
- 退出：托盘菜单"退出程序"；关闭窗口仅最小化到托盘

## 已知限制

- 分类过滤器中的 `doc:`/`pic:`/`video:`/`audio:`/`archive:`/`exe:` 为 Everything 1.5+ 搜索函数，1.4 下会退化为普通关键词。
- 删除操作不可恢复（永久删除模式），请谨慎使用；回收站模式走 send2trash。
