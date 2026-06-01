from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional

from .config import SourceConfig
from .model import FilingRef, Filing


class AbstractSource(ABC):
    """
    数据源抽象

    每个具体数据源(cninfo/SSE/HKEX)实现此接口。
    生命周期: init → discover → fetch (per ref) → close
    """

    def __init__(self, name: str, config: SourceConfig):
        self.name = name
        self.config = config

    @property
    def watchlist(self) -> List[dict]:
        return self.config.watchlist or []

    @property
    def options(self) -> dict:
        return self.config.options or {}

    @abstractmethod
    def discover(self, watchlist: Optional[List[dict]] = None) -> List[FilingRef]:
        """
        发现新的财报文件。

        watchlist: 监控列表，每项包含 stock, kinds, filters 等。
        返回 FilingRef 列表（不包含文件内容）。
        """
        ...

    @abstractmethod
    def fetch(self, ref: FilingRef) -> Optional[Filing]:
        """
        根据 FilingRef 下载完整文件内容。
        返回 Filing (包含 bytes content) 或 None (失败)。
        """
        ...

    def close(self):
        """释放资源 (可选重写)"""
        pass
