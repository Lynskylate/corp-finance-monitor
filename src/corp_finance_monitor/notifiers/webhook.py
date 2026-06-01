"""
Webhook notifier — POST filing metadata to a URL.

Payload format:
{
    "event": "filing_fetched",
    "subscription": {"id": ..., "name": ..., ...},
    "filing": {
        "source": "cninfo",
        "stock_code": "000725",
        "title": "2025年年度报告",
        "kind": "annual",
        "published_at": "2026-04-01",
        "url": "https://...",
        "stored_path": "/data/cninfo/..."
    }
}

The target URL is taken from the subscription's `target` field.
"""
from __future__ import annotations
import json
import logging
from typing import Optional

from corp_finance_monitor.core.model import FilingRef, Subscription
from .base import AbstractNotifier, NotifierResult

logger = logging.getLogger("cfm.notifier.webhook")

try:
    import requests
except ImportError:
    requests = None  # type: ignore


class WebhookNotifier(AbstractNotifier):
    """POST filing metadata to a webhook URL."""

    def __init__(self, timeout: int = 15, max_retries: int = 2):
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def channel(self) -> str:
        return "webhook"

    def match(self, target: str) -> bool:
        return target.startswith("http://") or target.startswith("https://")

    def send(
        self,
        subscription: Subscription,
        ref: FilingRef,
        stored_path: Optional[str] = None,
    ) -> NotifierResult:
        if requests is None:
            return NotifierResult(
                success=False,
                channel=self.channel,
                target=subscription.target,
                message="requests library not installed",
            )

        payload = {
            "event": "filing_fetched",
            "subscription": {
                "id": subscription.id,
                "name": subscription.name,
                "source": subscription.source,
                "stock_code": subscription.stock_code,
                "kind": subscription.kind,
            },
            "filing": {
                "source": ref.source,
                "source_id": ref.source_id,
                "stock_code": ref.stock_code,
                "stock_name": ref.stock_name,
                "title": ref.title,
                "kind": ref.kind.value,
                "published_at": ref.published_at,
                "url": ref.url,
                "stored_path": stored_path or "",
            },
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(
                    subscription.target,
                    json=payload,
                    timeout=self.timeout,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code < 400:
                    logger.info(
                        "Webhook OK: %s → %s (status %d)",
                        ref.title[:40],
                        subscription.target,
                        resp.status_code,
                    )
                    return NotifierResult(
                        success=True,
                        channel=self.channel,
                        target=subscription.target,
                        status_code=resp.status_code,
                    )
                logger.warning(
                    "Webhook error: %s returned %d",
                    subscription.target,
                    resp.status_code,
                )
                return NotifierResult(
                    success=False,
                    channel=self.channel,
                    target=subscription.target,
                    status_code=resp.status_code,
                    message=f"HTTP {resp.status_code}",
                )
            except Exception as e:
                logger.warning(
                    "Webhook attempt %d/%d failed: %s - %s",
                    attempt,
                    self.max_retries,
                    subscription.target,
                    e,
                )

        return NotifierResult(
            success=False,
            channel=self.channel,
            target=subscription.target,
            message=f"Failed after {self.max_retries} attempts",
        )
