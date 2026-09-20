"""运行历史：SQLModel + SQLite 记录每个文件被打开/运行的次数与最后时间。

数据表 FileRun（path 主键），SQLite 文件位于 %APPDATA%/CSearch/runs.db。
所有写读均容错：数据库异常时静默降级，不影响搜索主流程。

**惰性导入**：``sqlmodel`` + ``sqlalchemy`` 的导入代价约 1.2s，而它属于「打开文件才有
价值」的能力，因此模型与引擎都推迟到首次真正访问数据库时才构建（见 preload.py）。
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

_DIR = Path(os.environ.get("APPDATA", Path.home())) / "CSearch"
_DB_PATH = _DIR / "runs.db"

_lock = threading.Lock()
_engine: Any = None
_model_cls: Any = None


def _model() -> Any:
    """惰性构建 FileRun 模型（SQLModel 元数据只允许注册一次，故加锁缓存）。"""
    global _model_cls
    if _model_cls is None:
        with _lock:
            if _model_cls is None:
                from sqlmodel import Field, SQLModel

                class FileRun(SQLModel, table=True):
                    """文件运行记录：path 唯一，run_count 累计次数，last_run 最后运行时间。"""

                    path: str = Field(primary_key=True)
                    run_count: int = 0
                    last_run: datetime | None = None

                _model_cls = FileRun
    return _model_cls


def _db() -> Any:
    """惰性构建 SQLite 引擎（首次访问时才建目录与引擎）。"""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                from sqlmodel import create_engine

                _DIR.mkdir(parents=True, exist_ok=True)
                _engine = create_engine(
                    f"sqlite:///{_DB_PATH.as_posix()}",  # Windows 绝对路径需正斜杠
                    connect_args={"check_same_thread": False},  # 供线程池多线程访问
                )
    return _engine


def init_db() -> None:
    """建表（幂等）。"""
    try:
        from sqlmodel import SQLModel

        model = _model()
        SQLModel.metadata.create_all(_db(), tables=[model.__table__])  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def get_counts(paths: Iterable[str]) -> dict[str, int]:
    """批量查询运行次数：{path: run_count}。"""
    paths = [p for p in paths if p]
    if not paths:
        return {}
    try:
        from sqlalchemy import select
        from sqlmodel import Session

        model = _model()
        # 显式列选择：exec(select(Model.col, ...)) 返回行元组，取列更稳
        stmt = select(model.path, model.run_count).where(model.path.in_(paths))
        with Session(_db()) as session:
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
        from sqlmodel import Session

        model = _model()
        with Session(_db()) as session:
            for path in paths:
                row = session.get(model, path)
                if row is None:
                    session.add(model(path=path, run_count=1, last_run=now))
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
        from sqlmodel import Session

        model = _model()
        with Session(_db()) as session:
            row = session.get(model, path)
            if row is None:
                session.add(model(path=path, run_count=count, last_run=now))
            else:
                row.run_count = count
                row.last_run = now
            session.commit()
    except Exception:  # noqa: BLE001
        pass
