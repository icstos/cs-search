"""项目级资源目录定位（改前先读）。

src 布局下包位于 ``<项目根>/src/csearch``，而 flet 打包产物会把包摊平到
``<项目根>/csearch``。bootstrap 与 tray 原先各数一次 ``__file__`` 的 dirname
层级，布局一变就静默失效：图标找不到、assets_dir 指到 src 内部。
统一改为向上逐级寻找真实存在的 assets 目录；均未命中时回退到源码树中的
规范位置，由调用方自行容错（缺失资源本就有降级路径）。
"""

from __future__ import annotations

from pathlib import Path

_ASSETS_NAME = "assets"


def assets_dir() -> Path:
    """返回项目 assets 目录；目录可能尚不存在，由调用方决定如何降级。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / _ASSETS_NAME
        if candidate.is_dir():
            return candidate
    # src/csearch/_paths.py 的上三级为项目根；摊平结构下 assets 通常已在上循环命中
    return here.parents[2] / _ASSETS_NAME
