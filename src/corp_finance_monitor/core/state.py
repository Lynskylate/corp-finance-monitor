from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional

from .model import FilingRef, RunRecord, Subscription


class AbstractStateStore(ABC):
    """状态存储抽象：去重、运行记录、订阅管理、扫描进度。"""

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

    # --- Scan progress (Phase 3: checkpoint/resume) ---

    @abstractmethod
    def mark_scan_done(self, source: str, stock_code: str) -> None:
        """Mark a single stock as fully scanned for the current scan run."""
        ...

    @abstractmethod
    def is_scan_done(self, source: str, stock_code: str) -> bool:
        """Check if a stock has already been scanned in the current run."""
        ...

    @abstractmethod
    def count_scan_progress(self, source: str) -> tuple[int, int]:
        """Return (done_count, total_count) for a source's current scan."""
        ...

    @abstractmethod
    def clear_scan_progress(self, source: Optional[str] = None) -> None:
        """Clear scan progress. If source is None, clear all sources."""
        ...

    @abstractmethod
    def close(self):
        ...
