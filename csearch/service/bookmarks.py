"""书签服务：承载书签的业务规则（默认命名、ID 生成、增删改），持久化交给端口。"""

from __future__ import annotations

import uuid

from csearch.models.entities import Bookmark
from csearch.models.ports import BookmarkStore


class BookmarkService:
    """书签增删改查（内存列表 + JSON 持久化）。"""

    def __init__(self, store: BookmarkStore) -> None:
        self._store = store

    def load(self) -> list[Bookmark]:
        return self._store.load_bookmarks()

    def add(
        self,
        bookmarks: list[Bookmark],
        name: str,
        query: str,
        category: str,
        time_range: str,
        size_range: str,
    ) -> list[Bookmark]:
        """追加一条书签（名称为空则用「未命名书签」）并落盘，返回新列表。

        返回新列表对象（而非原地 append）是为了让 UI 层的「值比较/同一性」能感知
        变更，从而触发书签面板重绘。
        """
        bookmark = Bookmark(
            id=uuid.uuid4().hex[:12],
            name=name.strip() or "未命名书签",
            query=query,
            category=category,
            time_range=time_range,
            size_range=size_range,
        )
        updated = [*bookmarks, bookmark]
        self._store.save_bookmarks(updated)
        return updated

    def rename(self, bookmarks: list[Bookmark], bookmark_id: str, name: str) -> list[Bookmark]:
        """重命名（空名保留原名）并落盘，返回新列表。"""
        updated = list(bookmarks)
        for bookmark in updated:
            if bookmark.id == bookmark_id:
                bookmark.name = name.strip() or bookmark.name
                break
        self._store.save_bookmarks(updated)
        return updated

    def remove(self, bookmarks: list[Bookmark], bookmark_id: str) -> list[Bookmark]:
        """删除并落盘，返回剩余书签列表。"""
        remaining = [b for b in bookmarks if b.id != bookmark_id]
        self._store.save_bookmarks(remaining)
        return remaining
