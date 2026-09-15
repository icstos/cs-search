"""本地 JSON 持久化：应用配置 + 书签（%APPDATA%/CSearch/）。

- 读取容错：文件缺失/损坏/字段非法时回退默认值，绝不抛到上层；
- 写入原子化：先写临时文件再替换，避免写一半崩溃导致配置损坏；
- 配置按 key 合并：保存窗口几何/热键时保留其余字段。
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from csearch.models import AppConfig, Bookmark, WindowGeometry

_DIR = Path(os.environ.get("APPDATA", Path.home())) / "CSearch"
_CFG_PATH = _DIR / "config.json"
_BM_PATH = _DIR / "bookmarks.json"

_DEFAULT_GEO = WindowGeometry()
_BOOKMARK_FIELDS = {f.name for f in fields(Bookmark)}


def _load(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(path: Path, data: object) -> None:
    try:
        _DIR.mkdir(parents=True, exist_ok=True)
        # 同目录临时文件 + os.replace 原子替换
        fd, tmp = tempfile.mkstemp(dir=_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    except Exception:  # noqa: BLE001
        pass


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------- 配置
def load_config() -> AppConfig:
    raw = _load(_CFG_PATH)
    win = raw.get("window")
    win = win if isinstance(win, dict) else {}
    geo = WindowGeometry(
        width=_as_int(win.get("width"), _DEFAULT_GEO.width),
        height=_as_int(win.get("height"), _DEFAULT_GEO.height),
        left=win.get("left"),
        top=win.get("top"),
        maximized=bool(win.get("maximized", False)),
    )
    hotkey = str(raw.get("hotkey", "alt+space")).strip() or "alt+space"
    return AppConfig(window=geo, hotkey=hotkey,
                     start_hidden=bool(raw.get("start_hidden", False)))


def save_window(geo: WindowGeometry) -> None:
    raw = _load(_CFG_PATH)
    raw["window"] = {k: v for k, v in asdict(geo).items() if v is not None}
    _save(_CFG_PATH, raw)


def save_hotkey(hotkey: str) -> None:
    raw = _load(_CFG_PATH)
    raw["hotkey"] = hotkey
    _save(_CFG_PATH, raw)


# --------------------------------------------------------------------- 书签
def load_bookmarks() -> list[Bookmark]:
    try:
        with _BM_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(data, list):
        return []
    bookmarks: list[Bookmark] = []
    for item in data:
        # 仅取已知字段且必须含 id，单条损坏不影响其余
        if not isinstance(item, dict) or "id" not in item:
            continue
        try:
            bookmarks.append(Bookmark(**{k: v for k, v in item.items() if k in _BOOKMARK_FIELDS}))
        except TypeError:
            continue
    return bookmarks


def save_bookmarks(bookmarks: list[Bookmark]) -> None:
    _save(_BM_PATH, [asdict(b) for b in bookmarks])


def add_bookmark(bookmarks: list[Bookmark], name: str, query: str, category: str,
                 time_range: str, size_range: str) -> Bookmark:
    bm = Bookmark(
        id=uuid.uuid4().hex[:12],
        name=name.strip() or "未命名书签",
        query=query,
        category=category,
        time_range=time_range,
        size_range=size_range,
    )
    bookmarks.append(bm)
    save_bookmarks(bookmarks)
    return bm


def rename_bookmark(bookmarks: list[Bookmark], bm_id: str, name: str) -> None:
    for bm in bookmarks:
        if bm.id == bm_id:
            bm.name = name.strip() or bm.name
            break
    save_bookmarks(bookmarks)


def remove_bookmark(bookmarks: list[Bookmark], bm_id: str) -> None:
    save_bookmarks([b for b in bookmarks if b.id != bm_id])
