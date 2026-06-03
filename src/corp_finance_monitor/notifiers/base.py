"""
Abstract notifier — base class for all delivery backends.

Each notifier handles one delivery channel (webhook, email, wechat, etc.).
The Engine calls NotifierRegistry.dispatch() after each successful fetch.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from corp_finance_monitor.core.model import FilingRef, Subscription


@dataclass
class NotifierResult:
    """Result of a single notification attempt."""

    success: bool
    channel: str  # e.g. "webhook", "email", "wechat"
    target: str  # e.g. URL, email address
    message: str = ""  # Human-readable status or error
    status_code: int = 0  # HTTP status for webhook, etc.


class AbstractNotifier(ABC):
    """
    Delivery backend abstract base class.

    Subclasses implement `send()` for a specific channel.
    The `match()` method determines if a subscription target belongs
    to this notifier (e.g. URLs starting with "https://" → webhook).
    """

    @property
    @abstractmethod
    def channel(self) -> str:
        """Channel name (e.g. 'webhook', 'email', 'wechat')."""
        ...

    @abstractmethod
    def match(self, target: str) -> bool:
        """Return True if this notifier handles the given target string."""
        ...

    @abstractmethod
    def send(
        self,
        subscription: Subscription,
        ref: FilingRef,
        stored_path: str | None = None,
    ) -> NotifierResult:
        """
        Send a notification for a newly fetched filing.

        subscription: the subscription that matched this filing
        ref: the filing reference (metadata)
        stored_path: local file path of the downloaded filing (if available)
        """
        ...
