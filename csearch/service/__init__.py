"""服务层：编排核心业务流程，只依赖 ``csearch.models.ports`` 抽象接口。

- 不 import 任何 ``csearch.infra`` 具体实现（依赖倒置，具体实现由组合根注入）；
- 不 import 任何 ``csearch.viewmodel`` / ``csearch.view``（只允许被它们依赖）。
"""

from csearch.service.bookmarks import BookmarkService
from csearch.service.config import ConfigService
from csearch.service.files import FileService
from csearch.service.history import HistoryService
from csearch.service.search import SearchService
from csearch.service.session import SessionService

__all__ = [
    "BookmarkService",
    "ConfigService",
    "FileService",
    "HistoryService",
    "SearchService",
    "SessionService",
]
