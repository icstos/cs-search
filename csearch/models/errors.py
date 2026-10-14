"""领域错误类型。

放在 models 层是为了让「抛出方（infra）」与「捕获方（viewmodel）」都能依赖它，
而无需 viewmodel 反向依赖 infra——依赖倒置下，错误语义属于领域契约的一部分。
"""

from __future__ import annotations


class EngineUnavailableError(RuntimeError):
    """Everything 服务不可用（未运行 / SDK 加载失败 / 连接断开）。"""


class SearchTimeoutError(RuntimeError):
    """查询超时（内容扫描等耗时操作），已安全中止。"""
