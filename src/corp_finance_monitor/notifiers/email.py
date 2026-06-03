"""
Email notifier — stub for future email delivery.

Target format: "email:user@example.com"
Requires SMTP configuration (to be added via config.yaml).
"""

from __future__ import annotations

import logging

from corp_finance_monitor.core.model import FilingRef, Subscription

from .base import AbstractNotifier, NotifierResult

logger = logging.getLogger("cfm.notifier.email")


class EmailNotifier(AbstractNotifier):
    """
    Email delivery backend (stub).

    To implement:
    1. Add SMTP config to config.yaml (smtp_host, smtp_port, smtp_user, smtp_pass)
    2. Implement send() using smtplib + email.mime
    3. Build a plain-text or HTML email with filing metadata + download link
    """

    @property
    def channel(self) -> str:
        return "email"

    def match(self, target: str) -> bool:
        return target.startswith("email:")

    def send(
        self,
        subscription: Subscription,
        ref: FilingRef,
        stored_path: str | None = None,
    ) -> NotifierResult:
        email_addr = subscription.target.removeprefix("email:")
        logger.info(
            "Email notification (stub): would send to %s about '%s'",
            email_addr,
            ref.title[:40],
        )
        return NotifierResult(
            success=False,
            channel=self.channel,
            target=subscription.target,
            message="Email notifier not yet implemented (stub)",
        )
