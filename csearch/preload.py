"""后台预加载：把重依赖的导入从启动关键路径上摘下来。

为什么要这么做（时序依据，改前先读）：

``main.py`` → ``ft.run(boot)`` 内部的顺序是
``asyncio.run`` → ``FletSocketServer.start()``（**这一步才去拉起桌面客户端 flet.exe**）
→ 客户端连上后才回调 ``boot``。也就是说，**模块导入全部发生在客户端进程启动之前**，
两者是纯串行关系。而本项目的导入里，真正的大头都不在 flet 上：

- ``sqlmodel`` + ``sqlalchemy``（运行历史）      ~1.2s
- ``everytools``（连带 ``requests``/``charset_normalizer``） ~0.9s
- ``pystray`` + ``Pillow`` + ``pynput``（托盘/热键） ~0.8s
- ``pyperclip`` + ``send2trash``（文件操作）      ~0.1s

在导入期就把它们丢给守护线程去做，主线程立刻返回并进入 ``ft.run``，于是
「拉起并初始化桌面客户端」这段时间被拿来做导入，二者并行。实测可省下约 0.6~0.9s
的开窗时间（取决于客户端自身启动快慢）。

使用方式：
- ``start()`` 在 ``csearch.bootstrap`` 模块导入时调用（即 ``ft.run`` 之前）；
- ``wait()`` 在 ``boot`` 里等待完成（放到线程池里等，别阻塞事件循环）；
- 任何一层导入失败都会记在 ``error()`` 里，由调用方决定怎么提示，绝不让启动线程裸崩。
"""

from __future__ import annotations

import importlib
import threading
import traceback

# 需要预热的重模块：按「导入图顺序」排列，避免重复触发同一棵子树
_MODULES: tuple[str, ...] = (
    "csearch.history",        # sqlmodel / sqlalchemy
    "csearch.ops",            # pyperclip / send2trash
    "csearch.tray_manager",   # pystray / Pillow / pynput
    "csearch.engine",         # everytools（连带 requests）
    "csearch.state",          # 组装 Services（会加载 Everything DLL）
    "csearch.controller",     # 控制器门面
    "csearch.ui.app",         # 界面根组件
)

_done = threading.Event()
_error: BaseException | None = None
_error_traceback = ""
_thread: threading.Thread | None = None


def _run() -> None:
    global _error, _error_traceback
    try:
        for name in _MODULES:
            importlib.import_module(name)
    except BaseException as e:  # noqa: BLE001 —— 预加载失败必须留给 boot 决定如何降级
        _error = e
        _error_traceback = traceback.format_exc()
    finally:
        _done.set()


def start() -> None:
    """启动预加载线程（幂等）。"""
    global _thread
    if _thread is not None:
        return
    _thread = threading.Thread(target=_run, name="csearch-preload", daemon=True)
    _thread.start()


def done() -> bool:
    """预加载是否已结束（无论成功失败）。"""
    return _done.is_set()


def wait(timeout: float | None = None) -> bool:
    """等待预加载结束（阻塞）。调用方应放在 ``asyncio.to_thread`` 里。"""
    return _done.wait(timeout)


def error() -> BaseException | None:
    """预加载期间的异常（无则 None）。"""
    return _error


def error_traceback() -> str:
    """预加载异常的完整回溯文本（便于排查，勿上抛）。"""
    return _error_traceback
