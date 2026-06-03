"""
WeChat notifier — stub for future WeChat Work (企业微信) delivery.

Target format: "wechat:webhook_url" or "wechat:user_id"
Requires WeChat Work bot or message API configuration.
"""

from __future__ import annotations

import logging

from corp_finance_monitor.core.model import FilingRef, Subscription

from .base import AbstractNotifier, NotifierResult

logger = logging.getLogger("cfm.notifier.wechat")


class WeChatNotifier(AbstractNotifier):
    """
    WeChat Work delivery backend (stub).

    To implement:
    1. Add WeChat Work config to config.yaml (corp_id, agent_id, secret)
    2. For bot webhooks: POST markdown message to target URL
    3. For user messages: use WeChat Work message API
    """

    @property
    def channel(self) -> str:
        return "wechat"

    def match(self, target: str) -> bool:
        return target.startswith("wechat:")

    def send(
        self,
        subscription: Subscription,
        ref: FilingRef,
        stored_path: str | None = None,
    ) -> NotifierResult:
        wechat_target = subscription.target.removeprefix("wechat:")
        logger.info(
            "WeChat notification (stub): would send to %s about '%s'",
            wechat_target,
            ref.title[:40],
        )
        return NotifierResult(
            success=False,
            channel=self.channel,
            target=subscription.target,
            message="WeChat notifier not yet implemented (stub)",
        )
