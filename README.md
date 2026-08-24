# CSearch — Everything 1.5 极速文件搜索（Flet + everytools）

在 Windows 10/11 上复刻 Everything 的本地文件搜索体验：毫秒级回显、Everything 原生搜索语法、
实时索引同步、系统托盘常驻、全局热键唤起。**完全基于 Everything 1.5，不兼容 1.4。**

## 快速开始

```powershell
cd D:\projects\cs-search
pip install -e .          # 安装依赖（flet / everytools / requests / pynput / pyperclip / Send2Trash）
python main.py            # 启动
```

前置条件：本机已安装并运行 [Everything 1.5+](https://www.voidtools.com/zh-cn/downloads/)。
程序启动时自动检测 Everything 服务，未运行时在界面给出友好提示与一键启动引导。

## 功能总览

1. 极速搜索：输入防抖 300ms，Everything 原生语法（关键词 / 通配符 / 正则 / `ext:` / `content:` 等），
   结果懒加载（首批 200 条，滚动触底增量加载），表头点击切换排序。
2. 实时索引同步：5s 轻量签名轮询（offset=0, max=3，毫秒级）静默刷新结果，保留选中状态；
   若将官方 1.5 SDK DLL 放入 `vendor/`（或 `%APPDATA%/CSearch/sdk/`），自动启用
   `Everything_SetNotifyWindow` 事件驱动通知（托盘线程收消息，实时刷新）。
3. 文件操作：右键菜单 + 快捷键，支持多选批量（打开 / 定位 / 复制路径 / 复制文件名 /
   回收站删除 / 永久删除，删除前二次确认）。
4. 多维过滤：分类（全部/文件夹/文档/图片/视频/音频/压缩包/可执行文件）、修改时间范围、文件大小区间。
   分类使用 Everything 原生函数（`folder:`/`doc:`/`pic:`/`video:`/`audio:`/`exe:`），
   压缩包用 `ext:` 扩展名列表（`archive:` 函数在部分 1.5 配置下无效）。
5. 书签：保存"关键词+过滤器"组合，一键应用，支持重命名/删除，JSON 持久化。
6. 全局热键 + 系统托盘：默认 `Alt+Space` 唤起/隐藏（可在设置中自定义）；
   关闭窗口最小化到托盘（纯 ctypes Shell_NotifyIconW，零额外依赖），托盘右键菜单显示主窗口/退出。
7. 键盘导航：`↓` 搜索框→列表，`↑/↓` 移动选中，`Enter` 打开，`Esc` 清空搜索框，
   `F5` 刷新，`Ctrl+D` 复制路径，`Ctrl+E` 打开所在位置。
8. 窗口状态记忆：自动保存/恢复窗口尺寸与位置。

## 架构

```
main.py                  入口：窗口初始化、事件注册、渲染 App
csearch/
├── config.py            配置读写（窗口几何/热键，JSON 持久化，%APPDATA%/CSearch）
├── state.py             全局状态（@ft.observable dataclass）+ 服务单例 + 事件桥
├── search_engine.py     搜索内核：everytools 装载 SDK + 分页查询 + 排序 + 索引监听
├── file_ops.py          文件操作（os.startfile / explorer /select / pyperclip / send2trash）
├── bookmarks.py         书签 CRUD（JSON 持久化）
├── hotkey_tray.py       全局热键（pynput）+ 系统托盘（ctypes Shell_NotifyIcon）
├── controller.py        业务编排：防抖搜索、懒加载、静默刷新、菜单动作、对话框逻辑
├── icons.py             文件类型 → 图标/颜色 映射
├── logger.py            文件日志（%APPDATA%/CSearch/csearch.log）
└── ui/                  声明式组件：search_bar / sidebar / result_list / status_bar / dialogs / app
```

## 关键设计说明（Everything 1.5 实测验证）

- 分页查询：`Everything_SetMax/SetOffset` 限制单次 IPC 传输量（200 行/页），实测 29 万结果首屏
  15~80ms，总数经 `Everything_GetTotResults` 一次获取（全量传输需数秒，已弃用）。
- 排序常量：实测 1.5 服务器经 IPC 仍使用顺序式常量（官方 SDK 头文件一致）——
  名称 1/2、路径 3/4、大小 5/6、修改时间 13/14；负值/带符号常量会被服务器忽略并回退默认排序。
  `everytools.SortType` 枚举与此一致。
- 异步铁律：所有 SDK 同步调用一律经 `asyncio.to_thread` 放入线程池 + `threading.Lock` 串行化，
  Flet 事件循环零阻塞。
- 查询看门狗（5s）：`content:` 内容搜索在未启用内容索引时触发实时扫描，可能很慢；
  超时后安全中止（不触碰 DLL——卡死查询线程会让 `Everything_Reset` 永久阻塞，已实证规避），
  界面提示"需在 Everything 中启用内容索引"。超时期间新查询会收到"仍在后台执行"提示，
  待服务器扫描结束后自动恢复。
- SDK 适配：`Everything_GetResultFullPathNameW` 在 everytools 中 ctypes 签名错误，引擎已修正
  （(int, LPWSTR, int) -> int 两段式调用）。
- 声明式 UI：`UI = f(state)`，组件仅用 `use_state/use_effect/use_dialog/use_memo`；
  注意 flet 0.86 的 `PopupMenuItem` 用 `content=` 而非 `text=`。

## 配置与数据

- 配置/书签：`%APPDATA%/CSearch/config.json` + `bookmarks.json`
- 日志：`%APPDATA%/CSearch/csearch.log`
- 退出：托盘菜单"退出程序"；关闭窗口仅最小化到托盘

## 已知限制

- `content:` 内容搜索依赖 Everything 的"内容索引"设置（Tools > Options > Content），未启用时较慢。
- 索引变更通知默认走 5s 轮询；放置官方 1.5 SDK DLL 到 `vendor/` 后自动升级为事件驱动。
- 永久删除不可恢复，请谨慎使用；回收站模式走 send2trash。
