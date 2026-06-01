"""
Notifier registry — routes subscription targets to the right notifier.

Usage:
    registry = NotifierRegistry()
    registry.register(WebhookNotifier())
    registry.register(EmailNotifier())
    registry.register(WeChatNotifier())

    # After fetching a filing:
    results = registry.dispatch(subscriptions, ref, stored_path)
"""
from __future__ import annotations
import logging
from typing import List, Optional

from corp_finance_monitor.core.model import FilingRef, Subscription
from .base import AbstractNotifier, NotifierResult

logger = logging.getLogger("cfm.notifier.registry")


class NotifierRegistry:
    """Routes subscription targets to the correct notifier backend."""

    def __init__(self):
        self._notifiers: List[AbstractNotifier] = []

    def register(self, notifier: AbstractNotifier):
        self._notifiers.append(notifier)

    def _resolve(self, target: str) -> Optional[AbstractNotifier]:
        """Find the first notifier that handles this target."""
        for n in self._notifiers:
            if n.match(target):
                return n
        return None

    def dispatch(
        self,
        subscriptions: List[Subscription],
        ref: FilingRef,
        stored_path: Optional[str] = None,
    ) -> List[NotifierResult]:
        """
        Send notifications for a filing to all matching subscriptions.

        A subscription matches if:
        - source matches (or subscription.source is empty)
        - stock_code matches (or subscription.stock_code is empty)
        - kind matches (or subscription.kind is empty)
        - target has a registered notifier

        Returns one NotifierResult per notification attempted.
        """
        results: List[NotifierResult] = []

        for sub in subscriptions:
            if not sub.active:
                continue

            # Filter: does this subscription match the filing?
            if sub.source and sub.source != ref.source:
                continue
            if sub.stock_code and sub.stock_code != ref.stock_code:
                continue
            if sub.kind and sub.kind != ref.kind.value:
                continue

            # Route to notifier
            notifier = self._resolve(sub.target)
            if notifier is None:
                logger.warning(
                    "No notifier registered for target: %s (subscription %s)",
                    sub.target,
                    sub.name,
                )
                continue

            try:
                result = notifier.send(sub, ref, stored_path)
                results.append(result)
            except Exception as e:
                logger.error(
                    "Notifier %s failed for subscription '%s': %s",
                    notifier.channel,
                    sub.name,
                    e,
                )
                results.append(NotifierResult(
                    success=False,
                    channel=notifier.channel,
                    target=sub.target,
                    message=str(e),
                ))

        return results
