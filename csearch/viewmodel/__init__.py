"""视图模型层：持有 UI 状态、驱动 UI 更新，中转业务调用与状态回调。

- 只依赖 ``service`` 层与 ``models``；
- 不 import 任何 ``csearch.infra``（基础设施只经 ``Services`` 里的端口出现）；
- 不操作任何 Flet 控件（滚动 / 提示等 UI 能力经 ``Notifier`` / ``ScrollTarget`` 端口下发）。
"""

from csearch.viewmodel.container import (
    Services,
    current_services,
    install,
)
from csearch.viewmodel.context import AppContext, current, set_current
from csearch.viewmodel.state import AppState

__all__ = [
    "AppContext",
    "AppState",
    "Services",
    "current",
    "current_services",
    "install",
    "set_current",
]
