"""配置持久化：窗口几何、热键等（本地 JSON 文件，%APPDATA%/CSearch/config.json）。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

APP_DIR_NAME = "CSearch"


def app_data_dir() -> str:
    """应用数据目录（Windows: %APPDATA%/CSearch），不存在则创建。"""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def config_path() -> str:
    return os.path.join(app_data_dir(), "config.json")


@dataclass
class WindowGeometry:
    width: int = 1040
    height: int = 680
    left: Optional[int] = None
    top: Optional[int] = None
    maximized: bool = False


@dataclass
class AppConfig:
    window: WindowGeometry = field(default_factory=WindowGeometry)
    hotkey: str = "alt+space"      # 全局热键组合，如 "alt+space" / "ctrl+shift+f"
    start_hidden: bool = False     # 启动时直接驻留托盘
    first_run: bool = True


class ConfigStore:
    """config.json 的读写封装。所有异常吞掉并回退默认值，保证程序不因配置损坏崩溃。"""

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = path or config_path()
        self._data: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception:
            self._data = {}

    def save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # 写失败不崩溃，下次启动仍是旧配置

    # ---- 窗口几何 ----
    def get_window(self) -> WindowGeometry:
        w = self._data.get("window", {})
        return WindowGeometry(
            width=int(w.get("width", 1040)),
            height=int(w.get("height", 680)),
            left=w.get("left"),
            top=w.get("top"),
            maximized=bool(w.get("maximized", False)),
        )

    def set_window(self, geo: WindowGeometry) -> None:
        d = asdict(geo)
        if d.get("left") is None:
            d.pop("left", None)
        if d.get("top") is None:
            d.pop("top", None)
        self._data["window"] = d
        self.save()

    # ---- 热键 ----
    def get_hotkey(self) -> str:
        hk = self._data.get("hotkey", "alt+space")
        return hk if isinstance(hk, str) and hk.strip() else "alt+space"

    def set_hotkey(self, combo: str) -> None:
        self._data["hotkey"] = combo.strip().lower()
        self.save()

    # ---- 启动隐藏 ----
    def get_start_hidden(self) -> bool:
        return bool(self._data.get("start_hidden", False))

    def set_start_hidden(self, flag: bool) -> None:
        self._data["start_hidden"] = bool(flag)
        self.save()

    # ---- 首启标记 ----
    def is_first_run(self) -> bool:
        return bool(self._data.get("first_run", True))

    def mark_started(self) -> None:
        self._data["first_run"] = False
        self.save()
