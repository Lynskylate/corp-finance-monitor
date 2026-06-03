from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from .config import SourceConfig
from .model import Filing, FilingRef


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
    def watchlist(self) -> list[dict]:
        return self.config.watchlist or []

    @property
    def options(self) -> dict:
        return self.config.options or {}

    @abstractmethod
    def discover(
        self,
        watchlist: list[dict] | None = None,
        since: str | None = None,
        only_stock_codes: Sequence[str] | None = None,
    ) -> list[FilingRef]:
        """
        发现新的财报文件。

        watchlist: 监控列表，每项包含 stock, kinds, filters 等。
        since: 仅发现此日期之后发布的文件 (YYYY-MM-DD)。
               数据源应尽量在 API 层面过滤以减少传输量。
        only_stock_codes: 可选股票代码白名单。主要给 full-market 批量分片使用；
               不支持的 source 可以忽略该参数。
        返回 FilingRef 列表（不包含文件内容）。
        """
        ...

    @abstractmethod
    def fetch(self, ref: FilingRef) -> Filing | None:
        """
        根据 FilingRef 下载完整文件内容。
        返回 Filing (包含 bytes content) 或 None (失败)。
        """
        ...

    def close(self):
        """释放资源 (可选重写)"""
        pass
