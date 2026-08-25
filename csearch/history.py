"""运行历史：SQLModel + SQLite 持久化每个文件被打开/运行的次数与最后时间。

数据表 FileRun（full_path 主键），CRUD 全部走 SQLAlchemy 会话；
SQLite 文件位于 %APPDATA%/CSearch/runs.db。
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Iterable

from sqlalchemy import select, update
from sqlmodel import Field, Session, SQLModel, create_engine

_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "CSearch")
_DB_PATH = os.path.join(_DIR, "runs.db")


class FileRun(SQLModel, table=True):
    """文件运行记录：full_path 唯一，run_count 累计次数，last_run 最后运行时间。"""

    path: str = Field(primary_key=True)
    run_count: int = 0
    last_run: datetime | None = None


_engine = create_engine(
    f"sqlite:///{_DB_PATH.replace(os.sep, '/')}",  # Windows 绝对路径需正斜杠
    connect_args={"check_same_thread": False},  # 供 asyncio.to_thread 多线程访问
)


def init_db() -> None:
    """建表（幂等）。"""
    try:
        os.makedirs(_DIR, exist_ok=True)
        SQLModel.metadata.create_all(_engine)
    except Exception:  # noqa: BLE001
        pass


def get_counts(paths: Iterable[str]) -> dict[str, int]:
    """批量查询运行次数：{full_path: run_count}。"""
    paths = [p for p in paths if p]
    if not paths:
        return {}
    try:
        # 显式列选择：SQLModel 0.0.39 的 exec(select(Model)) 返回 Row，取列更稳
        stmt = select(FileRun.path, FileRun.run_count).where(FileRun.path.in_(paths))
        with Session(_engine) as session:
            rows = session.exec(stmt).all()
        return {p: c for p, c in rows}
    except Exception:  # noqa: BLE001
        return {}


def increment(paths: Iterable[str]) -> None:
    """打开文件后递增运行次数（upsert，last_run 更新为当前时间）。"""
    paths = [p for p in paths if p]
    if not paths:
        return
    now = datetime.now()
    try:
        with Session(_engine) as session:
            for p in paths:
                row = session.get(FileRun, p)
                if row is None:
                    session.add(FileRun(path=p, run_count=1, last_run=now))
                else:
                    row.run_count += 1
                    row.last_run = now
            session.commit()
    except Exception:  # noqa: BLE001
        pass


def set_count(path: str, count: int) -> None:
    """右键设置运行次数（upsert）。"""
    if not path or count < 0:
        return
    now = datetime.now()
    try:
        with Session(_engine) as session:
            row = session.get(FileRun, path)
            if row is None:
                session.add(FileRun(path=path, run_count=count, last_run=now))
            else:
                row.run_count = count
                row.last_run = now
            session.commit()
    except Exception:  # noqa: BLE001
        pass
