"""
Push notification support for A2A Lite agents.

Usage:
    from a2a_lite.push_notifications import WebhookPushNotifier

    agent = Agent(
        name="Bot",
        description="...",
        push_notifier=WebhookPushNotifier(
            url="https://my-app.com/webhook/a2a",
            secret="my-signing-secret",  # optional HMAC-SHA256 signing
        ),
    )
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PushNotifier(ABC):
    """
    Abstract base class for push notification delivery.

    Implement this to send task completion events to external systems
    (webhooks, message queues, Slack, etc.).

    Example custom implementation:
        class SlackPushNotifier(PushNotifier):
            def __init__(self, webhook_url: str):
                self.url = webhook_url

            async def notify(self, event: dict) -> None:
                import httpx
                text = f"Skill `{event['skill']}` completed: {event['status']}"
                async with httpx.AsyncClient() as client:
                    await client.post(self.url, json={"text": text})
    """

    @abstractmethod
    async def notify(self, event: Dict[str, Any]) -> None:
        """
        Send a notification for a skill completion event.

        Args:
            event: dict with keys:
                - skill (str): the skill that completed
                - result (Any): the skill's return value
                - status (str): "completed" | "failed"
                - timestamp (float): unix timestamp
                - agent (str): agent name
        """
        ...


class WebhookPushNotifier(PushNotifier):
    """
    Sends skill completion events as HTTP POST requests to a webhook URL.

    Features:
    - Automatic retry with exponential backoff
    - Optional HMAC-SHA256 request signing
    - Configurable headers
    - Timeout protection

    Example:
        notifier = WebhookPushNotifier(
            url="https://api.example.com/a2a-events",
            secret="my-webhook-secret",
            headers={"Authorization": "Bearer token"},
            max_retries=3,
        )
    """

    def __init__(
        self,
        url: str,
        secret: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        max_retries: int = 3,
        timeout: float = 10.0,
    ) -> None:
        """
        Args:
            url: Webhook endpoint URL
            secret: Optional secret for HMAC-SHA256 request signing.
                    The signature is sent as X-A2A-Signature header.
            headers: Additional HTTP headers to include in requests.
            max_retries: Number of retry attempts on failure (default: 3).
            timeout: HTTP request timeout in seconds (default: 10.0).
        """
        self.url = url
        self.secret = secret
        self.headers = headers or {}
        self.max_retries = max_retries
        self.timeout = timeout

    def _sign_payload(self, payload: str) -> str:
        """Generate HMAC-SHA256 signature for the payload."""
        return hmac.new(
            self.secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def notify(self, event: Dict[str, Any]) -> None:
        """Send the event to the configured webhook URL with retries."""
        try:
            import httpx
        except ImportError:
            logger.error(
                "httpx is required for WebhookPushNotifier. "
                "Install it with: pip install httpx"
            )
            return

        payload = json.dumps(event, default=str)
        headers = {
            "Content-Type": "application/json",
            "X-A2A-Event": event.get("skill", "unknown"),
            **self.headers,
        }

        if self.secret:
            headers["X-A2A-Signature"] = f"sha256={self._sign_payload(payload)}"

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.url,
                        content=payload,
                        headers=headers,
                        timeout=self.timeout,
                    )
                    response.raise_for_status()
                    logger.debug(
                        "Push notification sent: skill=%s status=%s",
                        event.get("skill"),
                        response.status_code,
                    )
                    return
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(
                        "Push notification failed (attempt %d/%d), retrying in %ds: %s",
                        attempt + 1,
                        self.max_retries,
                        wait,
                        e,
                    )
                    import asyncio
                    await asyncio.sleep(wait)

        logger.error(
            "Push notification failed after %d attempts: %s",
            self.max_retries,
            last_error,
        )


class LogPushNotifier(PushNotifier):
    """
    Simple notifier that logs events. Useful for development and debugging.

    Example:
        agent = Agent(
            name="Bot",
            description="...",
            push_notifier=LogPushNotifier(level="INFO"),
        )
    """

    def __init__(self, level: str = "INFO") -> None:
        self.level = level.upper()

    async def notify(self, event: Dict[str, Any]) -> None:
        log_fn = getattr(logger, self.level.lower(), logger.info)
        log_fn(
            "[A2A Push] skill=%s status=%s timestamp=%s",
            event.get("skill"),
            event.get("status"),
            event.get("timestamp"),
        )
