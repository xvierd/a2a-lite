"""
Push notification support for A2A Lite agents.

Provides an ABC and two built-in implementations:
- LogPushNotifier  — writes events to the Python logger (great for dev)
- WebhookPushNotifier — POSTs JSON payloads to an HTTPS endpoint with
  optional HMAC-SHA256 request signing.
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
    """Abstract base class for push notifiers."""

    @abstractmethod
    async def notify(self, event: Dict[str, Any]) -> None:
        """Send a push notification for the given event payload.

        Args:
            event: Arbitrary dict describing the completed task / event.
        """


class LogPushNotifier(PushNotifier):
    """Development-friendly notifier that logs events instead of POSTing them.

    Example::

        notifier = LogPushNotifier()
        agent = Agent(name="Bot", description="...", push_notifier=notifier)
    """

    def __init__(self, level: int = logging.INFO) -> None:
        self._level = level

    async def notify(self, event: Dict[str, Any]) -> None:
        """Log the event at the configured log level."""
        logger.log(self._level, "PushNotifier event: %s", json.dumps(event, default=str))


class WebhookPushNotifier(PushNotifier):
    """Production-ready notifier that POSTs JSON events to a webhook URL.

    Supports optional HMAC-SHA256 request signing via the ``secret`` parameter.
    When a secret is provided every request includes an
    ``X-A2A-Signature: sha256=<hex>`` header that the receiver can verify.

    Args:
        url: The webhook endpoint URL.
        secret: Optional secret for HMAC-SHA256 signing.  The raw bytes (or a
            UTF-8 string) used as the HMAC key.
        timeout: HTTP request timeout in seconds (default 10).
        max_retries: How many times to retry on failure (default 1).

    Example::

        notifier = WebhookPushNotifier(
            url="https://hooks.example.com/a2a",
            secret=os.getenv("WEBHOOK_SECRET"),
        )
        agent = Agent(name="Bot", description="...", push_notifier=notifier)
    """

    def __init__(
        self,
        url: str,
        secret: Optional[str | bytes] = None,
        timeout: float = 10.0,
        max_retries: int = 1,
    ) -> None:
        self.url = url
        self._secret: Optional[bytes] = (
            secret.encode("utf-8") if isinstance(secret, str) else secret
        )
        self.timeout = timeout
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _sign(self, body: bytes) -> str:
        """Return the HMAC-SHA256 hex digest for *body* using the configured secret."""
        if self._secret is None:
            raise ValueError("No secret configured for signing")
        sig = hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        return f"sha256={sig}"

    def _build_headers(self, body: bytes) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._secret is not None:
            headers["X-A2A-Signature"] = self._sign(body)
        return headers

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def notify(self, event: Dict[str, Any]) -> None:
        """POST *event* as JSON to the webhook URL, retrying on transient failures."""
        import httpx

        body = json.dumps(event, default=str).encode("utf-8")
        headers = self._build_headers(body)

        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(self.url, content=body, headers=headers)
                if response.is_success:
                    return
                # Log and (possibly) retry on server-side errors
                logger.warning(
                    "Webhook returned %s for %s (attempt %d/%d)",
                    response.status_code,
                    self.url,
                    attempt + 1,
                    self.max_retries + 1,
                )
                last_exc = RuntimeError(
                    f"Webhook returned HTTP {response.status_code}"
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Webhook request to %s failed (attempt %d/%d): %s",
                    self.url,
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )
                last_exc = exc

        if last_exc is not None:
            raise last_exc
