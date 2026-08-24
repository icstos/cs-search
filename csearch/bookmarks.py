"""书签持久化：搜索条件（关键词+过滤器组合）的增删改查，JSON 文件存储。"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Optional

from csearch.config import app_data_dir


def bookmarks_path() -> str:
    return os.path.join(app_data_dir(), "bookmarks.json")


class BookmarkStore:
    """书签存储。每条书签：{id, name, query, category, time_range, size_range, created}。"""

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = path or bookmarks_path()
        self._items: list[dict[str, Any]] = []
        self.load()

    # ---- 持久化 ----
    def load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._items = [b for b in data if isinstance(b, dict)]
        except Exception:
            self._items = []

    def save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._items, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---- CRUD ----
    def all(self) -> list[dict[str, Any]]:
        return list(self._items)

    def get(self, bookmark_id: str) -> Optional[dict[str, Any]]:
        for b in self._items:
            if b.get("id") == bookmark_id:
                return b
        return None

    def add(self, name: str, query: str, category: str, time_range: str, size_range: str) -> dict[str, Any]:
        item = {
            "id": uuid.uuid4().hex[:12],
            "name": name.strip() or "未命名书签",
            "query": query,
            "category": category,
            "time_range": time_range,
            "size_range": size_range,
            "created": int(time.time()),
        }
        self._items.append(item)
        self.save()
        return item

    def rename(self, bookmark_id: str, new_name: str) -> bool:
        b = self.get(bookmark_id)
        if b is None:
            return False
        b["name"] = new_name.strip() or b["name"]
        self.save()
        return True

    def remove(self, bookmark_id: str) -> bool:
        before = len(self._items)
        self._items = [b for b in self._items if b.get("id") != bookmark_id]
        if len(self._items) != before:
            self.save()
            return True
        return False
