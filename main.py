"""CSearch 桌面应用入口（Everything 1.5 极速文件搜索）。

运行：python main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# 打包后 serious_python 的隔离环境不会执行 pip install -e .，csearch 会被编译到
# <app>/src/csearch/，而运行时 sys.path 只有 <app>/ 根目录（不含 src）。
# 这一行同时覆盖开发态（源码在 ./src）与打包态（pyc 在 ./src），删掉即打包报
# ModuleNotFoundError: No module named 'csearch'。2026-11-16 实测。
_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path and (_SRC / "csearch").exists():
    sys.path.insert(0, str(_SRC))

from csearch.bootstrap import run  # noqa: E402

if __name__ == "__main__":
    run()
