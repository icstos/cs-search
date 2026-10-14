"""配置服务：承载配置的业务规则（热键合法性回退），持久化交给端口。"""

from __future__ import annotations

from csearch.models.constants import DEFAULT_HOTKEY, is_valid_hotkey
from csearch.models.entities import AppConfig, WindowGeometry
from csearch.models.ports import ConfigStore


class ConfigService:
    """应用配置读写。"""

    def __init__(self, store: ConfigStore) -> None:
        self._store = store

    def load(self) -> AppConfig:
        """读取配置；热键非法时回退默认。

        为什么在服务层做回退：历史/手改配置里可能出现空转热键（纯修饰键、
        末尾多写 ``+`` 等），注册它会变成「按修饰键即唤起窗口」或直接注册失败
        导致全局唤起键彻底失效。此处统一兜底，读取方无需重复判断。
        """
        config = self._store.load_config()
        if not is_valid_hotkey(config.hotkey):
            config.hotkey = DEFAULT_HOTKEY
        return config

    def save_window(self, geometry: WindowGeometry) -> None:
        self._store.save_window(geometry)

    def save_hotkey(self, hotkey: str) -> None:
        self._store.save_hotkey(hotkey)
