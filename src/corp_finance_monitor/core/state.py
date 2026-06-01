from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional

from .model import FilingRef, RunRecord, Subscription


class AbstractStateStore(ABC):
    """状态存储抽象：去重、运行记录、订阅管理。"""

    @abstractmethod
    def initialize(self):
        ...

    @abstractmethod
    def has_filing(self, ref: FilingRef) -> bool:
        ...

    @abstractmethod
    def record_filing(self, ref: FilingRef, stored_path: str):
        ...

    @abstractmethod
    def record_run(
        self,
        started_at: str,
        finished_at: str,
        discovered: int,
        fetched: int,
        failed: int,
    ) -> int:
        ...

    @abstractmethod
    def list_runs(self, limit: int = 20) -> List[RunRecord]:
        ...

    @abstractmethod
    def last_successful_run_start(self) -> Optional[str]:
        """Return the started_at timestamp of the last successful run, or None."""
        ...

    @abstractmethod
    def create_subscription(self, subscription: Subscription) -> Subscription:
        ...

    @abstractmethod
    def list_subscriptions(
        self,
        source: Optional[str] = None,
        stock_code: Optional[str] = None,
        active_only: bool = False,
    ) -> List[Subscription]:
        ...

    @abstractmethod
    def close(self):
        ...
