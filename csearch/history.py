"""运行历史：SQLModel + SQLite 记录每个文件被打开/运行的次数与最后时间。

数据表 FileRun（path 主键），SQLite 文件位于 %APPDATA%/CSearch/runs.db。
所有写读均容错：数据库异常时静默降级，不影响搜索主流程。
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlmodel import Field, Session, SQLModel, create_engine

_DIR = Path(os.environ.get("APPDATA", Path.home())) / "CSearch"
_DB_PATH = _DIR / "runs.db"
_DIR.mkdir(parents=True, exist_ok=True)

_engine = create_engine(
    f"sqlite:///{_DB_PATH.as_posix()}",  # Windows 绝对路径需正斜杠
    connect_args={"check_same_thread": False},  # 供 asyncio.to_thread 多线程访问
)


class FileRun(SQLModel, table=True):
    """文件运行记录：path 唯一，run_count 累计次数，last_run 最后运行时间。"""

    path: str = Field(primary_key=True)
    run_count: int = 0
    last_run: datetime | None = None


def init_db() -> None:
    """建表（幂等）。"""
    try:
        SQLModel.metadata.create_all(_engine)
    except Exception:  # noqa: BLE001
        pass


def get_counts(paths: Iterable[str]) -> dict[str, int]:
    """批量查询运行次数：{path: run_count}。"""
    paths = [p for p in paths if p]
    if not paths:
        return {}
    try:
        # 显式列选择：exec(select(Model.col, ...)) 返回行元组，取列更稳
        stmt = select(FileRun.path, FileRun.run_count).where(FileRun.path.in_(paths))
        with Session(_engine) as session:
            rows = session.exec(stmt).all()
        return {path: count for path, count in rows}
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
            for path in paths:
                row = session.get(FileRun, path)
                if row is None:
                    session.add(FileRun(path=path, run_count=1, last_run=now))
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
