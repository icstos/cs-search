"""本地 JSON 持久化：应用配置 + 书签（%APPDATA%/CSearch/）。"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict

from csearch.types import AppConfig, Bookmark, WindowGeometry

_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "CSearch")
_CFG_PATH = os.path.join(_DIR, "config.json")
_BM_PATH = os.path.join(_DIR, "bookmarks.json")


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def _save(path: str, data: object) -> None:
    try:
        os.makedirs(_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- 配置
def load_config() -> AppConfig:
    raw = _load(_CFG_PATH)
    w = raw.get("window", {})
    geo = WindowGeometry(
        width=int(w.get("width", 1040)),
        height=int(w.get("height", 680)),
        left=w.get("left"),
        top=w.get("top"),
        maximized=bool(w.get("maximized", False)),
    )
    return AppConfig(
        window=geo,
        hotkey=str(raw.get("hotkey", "alt+space")).strip() or "alt+space",
        start_hidden=bool(raw.get("start_hidden", False)),
    )


def save_window(geo: WindowGeometry) -> None:
    raw = _load(_CFG_PATH)
    raw["window"] = {k: v for k, v in asdict(geo).items() if v is not None}
    _save(_CFG_PATH, raw)


def save_hotkey(hotkey: str) -> None:
    raw = _load(_CFG_PATH)
    raw["hotkey"] = hotkey
    _save(_CFG_PATH, raw)


# ---------------------------------------------------------------- 书签
def load_bookmarks() -> list[Bookmark]:
    data = _load(_BM_PATH)
    if not isinstance(data, list):
        return []
    return [Bookmark(**b) for b in data if isinstance(b, dict) and "id" in b]


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