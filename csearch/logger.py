"""轻量文件日志（%APPDATA%/CSearch/csearch.log），用于问题排查。"""

from __future__ import annotations

import logging
import os

from csearch.config import app_data_dir

_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        _logger = logging.getLogger("csearch")
        _logger.setLevel(logging.INFO)
        try:
            fh = logging.FileHandler(
                os.path.join(app_data_dir(), "csearch.log"), encoding="utf-8"
            )
            fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            _logger.addHandler(fh)
        except Exception:  # noqa: BLE001
            pass
    return _logger
