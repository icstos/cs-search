# CSearch — Everything 1.5 极速文件搜索

在 Windows 10/11 上复刻 Everything 的本地文件搜索体验：毫秒级回显、Everything 原生搜索语法、
实时索引同步、系统托盘常驻、全局热键唤起。**完全基于 Everything 1.5 + Python 3.12 + Flet 1.0.3。**

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
- 搜索框无内容时**不显示搜索结果**，结果区展示书签面板；输入即搜（防抖 100ms）。
- 书签卡片显示名称与条件摘要，点击应用、菜单重命名/删除。

## 功能

1. 极速搜索：输入防抖 100ms，Everything 原生语法（关键词 / 通配符 / 正则 / `ext:` / `content:`），
   结果懒加载（首批 200 条，滚动触底增量加载），表头点击切换四列排序。
2. 实时索引同步：外部程序（资源管理器等）增删改名文件后，结果列表**约 1 秒内**自动跟着变
   （新建/删除 0.4~0.9s、改名 1.06s，真机实测）；原地补丁式更新——不塌回一页、不跳回顶部、
   不受影响的行逐像素不变，选中按完整路径迁移，滚动位置保持不动。
3. 文件操作：右键菜单 + 快捷键，多选批量（打开 / 定位 / 复制路径 / 复制文件名 /
   删除），删除默认移入回收站（无需确认，可恢复）。
4. 多维过滤：分类（全部/文件夹/文档/图片/视频/音频/压缩包/可执行文件）、修改时间范围、大小区间。
5. 书签：保存"关键词+过滤器"组合，卡片式展示，一键应用，重命名/删除，JSON 持久化。
6. 全局热键 + 系统托盘：默认 `Alt+Space`（可自定义），关闭窗口最小化托盘
   （pystray 托盘 + pynput 热键，守护子线程运行，跨平台；托盘左键单击切换窗口、
   右键菜单 显示/隐藏/退出）。
7. 键盘导航：`↓` 搜索框→列表，`↑/↓` 移动选中，`Enter` 打开，`Delete` 删除到回收站（无需确认），
   `Esc` 清空，`F5` 刷新，`Ctrl+D` 复制路径，`Ctrl+E` 定位，`Ctrl+A` 全选。
8. 窗口状态记忆：自动保存/恢复尺寸位置。

## 架构（v4 重构：MVVM + 五层依赖倒置）

严格单向依赖，高层依赖抽象接口，禁止跨层与反向依赖：

```
View ──▶ ViewModel ──▶ Service ──▶ Infra
  └──────────┴───────────┴──────────┘
              Models（五层均可依赖）
```

```
main.py                  极简入口（委托 bootstrap.run）
app.py                   独立介绍站点（Flet 1.0.3，flet run app.py）
csearch/
├── bootstrap.py         组合根：装配 infra → service → viewmodel，接页面与全局事件
├── preload.py           启动预热（重依赖导入与客户端拉起并行）
├── models/              模型层：数据结构 / 枚举 / 常量 / 抽象接口，无业务逻辑
│   ├── constants.py     常量与界面调参（单一事实来源）
│   ├── enums.py         Focus / DialogKind / MenuKind / WindowEventKind / BridgeEventType
│   ├── entities.py      ResultItem / SearchOutcome / Bookmark / EngineStatus / 配置 / 事件
│   ├── errors.py        领域错误（EngineUnavailable / SearchTimeout）
│   └── ports.py         全部抽象接口（Protocol）：九大基础设施端口 + 视图/工厂端口
├── infra/               基础设施层：底层技术实现，不含业务逻辑
│   ├── everything_engine.py  Everything 1.5 SDK（分页查询 / 排序 / 内容搜索看门狗）
│   ├── file_ops.py           系统文件操作（打开 / 定位 / 复制 / 回收站 / 启动引擎）
│   ├── json_store.py         配置与书签 JSON（容错读取 + 原子写入）
│   ├── run_history.py        运行历史（SQLModel / SQLite，惰性导入）
│   ├── win32.py              Win32 能力（修饰键 / 光标 / 多屏几何 / 窗口置前）
│   ├── wheel.py              WH_MOUSE_LL 滚轮桥（部分客户端滚轮失效兜底）
│   ├── tray.py               托盘（pystray）+ 全局热键（pynput），守护线程
│   ├── event_bus.py          跨线程事件桥（后台线程 → asyncio 主循环）
│   ├── flet_window.py        Flet Page.window → Window 端口适配
│   ├── flet_events.py        Flet 事件 → KeyStroke / WindowEventData 归一化
│   ├── notifier.py           Flet SnackBar → Notifier 端口适配
│   └── background_factory.py 托盘 / 滚轮桥工厂（service 不感知具体类型）
├── service/             服务层：编排核心业务流程，只依赖抽象接口
│   ├── search.py        查询构建 → 分页检索 → 运行次数回填（一次线程往返）
│   ├── files.py         文件动作（全部入线程池）
│   ├── history.py       运行历史（同步仓储 → 异步 API）
│   ├── bookmarks.py     书签业务规则（默认命名 / ID 生成 / 增删改）
│   ├── config.py        配置业务规则（非法热键回退默认）
│   └── session.py       启动装配（后台服务 / 引擎探测 / 托盘 / 热键）与退出
├── viewmodel/           视图模型层：持有 UI 状态、中转业务调用与状态回调
│   ├── state.py         AppState（@ft.observable 单一状态源）
│   ├── container.py     Services（viewmodel 可见的全部能力，只含端口与 service）
│   ├── context.py       AppContext（state + 全部 VM，view 的唯一入口）
│   ├── search.py        防抖 / 分页 / 增量加载 / 静默刷新 / 排序过滤正则 / 滚动
│   ├── selection.py     选中 / 双击分发 / 键盘移动 / 焦点域
│   ├── actions.py       文件动作、运行次数、引擎引导
│   ├── bookmarks.py     书签保存 / 应用 / 重命名 / 删除
│   ├── columns.py       列宽拖拽（双通道）与缩放自适应
│   ├── settings.py      全局热键 / 自定义大小
│   ├── menu.py          右键菜单状态与坐标夹紧
│   ├── window.py        托盘显隐 / 唤回抢焦 / 几何记忆 / 窗口事件 / 退出
│   ├── keyboard.py      页面级快捷键路由
│   └── session.py       初始化编排 + 事件桥消费循环
└── view/                视图层：纯 Flet 组件，UI = f(状态)，无业务逻辑
    ├── theme.py         设计令牌（颜色/间距/边框/对齐，单一来源）
    ├── icons.py         文件类型 → 图标/颜色
    ├── events.py        事件坐标读取（交给 VM 的纯数据）
    ├── scroller.py      ListView → ScrollTarget 端口适配
    └── app / searchbar / results / bookmarks / statusbar / dialogs / menu / sidebar
```

分层落点：

| 层 | 允许依赖 | 禁止 |
| --- | --- | --- |
| models | 无（仅标准库） | 任何其它层 |
| infra | models | service / viewmodel / view |
| service | models（抽象接口） | infra 具体实现 / viewmodel / view |
| viewmodel | models、service | infra 具体实现 / view 控件 |
| view | models、viewmodel | service / infra |

设计要点：

- **依赖倒置**：service / viewmodel / view 只 import `models.ports` 里的 Protocol；
  具体实现在组合根 `bootstrap._build_services()` 里构造并注入，换实现不改调用方。
- **声明式范式**：`UI = f(state)`，组件仅用 `use_state/use_effect/use_memo/use_ref/use_dialog`，
  状态变更自动驱动重绘，无命令式控件操作。
- **VM 不碰控件**：滚动经 `ScrollTarget`、提示经 `Notifier`、窗口经 `Window`、
  屏幕能力经 `Screen` 端口下发；按键/窗口事件在 infra 归一化为
  `KeyStroke` / `WindowEventData` 后再进 VM。
- **异步铁律**：所有 SDK/系统同步调用在 service 层经 `asyncio.to_thread` 入线程池，
  事件循环零阻塞。
- **Python 3.12 原生语法**：`match-case`（键盘 / 窗口 / 桥事件 / 尺寸区间分发）、
  `int | None` 联合类型、`type` 别名、`StrEnum`、`Protocol`，无任何低版本兼容逻辑。
- **启动并行**：`preload` 在模块导入期把 everytools 的导入丢给守护线程，
  与「拉起桌面客户端」并行，省下约 0.6~0.9s 开窗时间。
- 其余性能要点（分页查询、结果分片落地、行控件缓存、双通道列宽拖拽、查询看门狗、
  排序常量、分类查询函数）与 v3 完全一致，均在各模块 docstring 中标注「改前先读」。


## 数据与启动

- 配置/书签：`%APPDATA%/CSearch/config.json` + `bookmarks.json`
- 启动即搜索：设置环境变量 `CSEARCH_QUERY=关键词`（如 `readme`）可在启动时自动执行该搜索；
  默认未设置时启动显示书签面板。
- 列宽调整：结果表头列间有分隔条（悬停高亮、光标变为双向箭头），按住并左右拖动即可调整
  各列宽度，窗口缩放时弹性列自动适配；拖拽中表头实时跟手、行按节流重排，保证流畅。
- 运行次数：结果列表含"次数"列，记录每个文件的打开/运行历史（SQLModel + SQLite，
  `%APPDATA%/CSearch/runs.db`）；打开文件自动 +1，右键菜单"设置运行次数"可手动调整；
  该列为本地数据，不参与 Everything 服务端排序。
- 退出：托盘菜单"退出程序"；关闭窗口仅最小化托盘

## 已知限制

- `content:` 需 Everything 启用内容索引（Tools > Options > Content），未启用时较慢并触发超时提示。
- 索引变更同步只能轮询：everytools 附带的 Everything64.dll 是 1.4 SDK，实测 90 个导出符号里
  没有任何变更通知 API（`SetReplyWindow` 只是「异步查询完成」的回执窗口）。因此由
  `viewmodel/search.py::sync_loop` 分两级探针轮询（浅探 700ms 一拍 / 全探每 3 拍），
  约 1.7% 单核开销，窗口隐藏到托盘时完全不探。
- 删除默认移入回收站（send2trash），可恢复，无需确认。
