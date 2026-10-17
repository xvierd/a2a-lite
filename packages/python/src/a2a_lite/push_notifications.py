"""
Push notification support for A2A Lite agents.

Usage (agent-level):
    from a2a_lite.push_notifications import WebhookPushNotifier

    agent = Agent(
        name="Bot",
        description="...",
        push_notifier=WebhookPushNotifier(
            url="https://my-app.com/webhook/a2a",
            secret="my-signing-secret",  # optional HMAC-SHA256 signing
        ),
    )

Usage (per-task):
    # Server-side: the SDK manages owner-scoped task configuration.
    # Client-side: use set_task_push_notification() or handle.subscribe().
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import socket
from abc import ABC, abstractmethod
from typing import Any

import httpx
from a2a.server.tasks import BasePushNotificationSender
from a2a.utils.proto_utils import to_stream_response
from a2a.utils.push_url_validator import validate_push_notification_url
from google.protobuf.json_format import MessageToDict

logger = logging.getLogger(__name__)
CALLBACK_DNS_TIMEOUT = 10.0
CALLBACK_DELIVERY_TIMEOUT = 10.0


# ---------------------------------------------------------------------------
# Legacy local registry and guarded SDK callback transport
# ---------------------------------------------------------------------------


class TaskPushRegistry:
    """Legacy standalone registry; protocol endpoints use the SDK scoped store.

    Prefer authenticated A2A push configuration operations for server callbacks.
    This local utility does not register callbacks on an Agent.
    """

    def __init__(self) -> None:
        self._configs: dict[str, dict] = {}

    def set(self, task_id: str, url: str, token: str | None = None) -> None:
        self._configs[task_id] = {"url": url, "token": token}

    def get(self, task_id: str) -> dict | None:
        return self._configs.get(task_id)

    def delete(self, task_id: str) -> bool:
        return self._configs.pop(task_id, None) is not None

    def __contains__(self, task_id: str) -> bool:
        return task_id in self._configs


async def _public_callback_addresses(url: httpx.URL) -> list[str]:
    if url.scheme != "https" or not url.host or url.userinfo or url.fragment:
        raise ValueError("Callback requires a public HTTPS URL without credentials or fragments")
    addresses = await asyncio.get_running_loop().getaddrinfo(url.host, url.port or 443, type=socket.SOCK_STREAM)
    ips = list(dict.fromkeys(str(ipaddress.ip_address(info[4][0])) for info in addresses))
    if not ips:
        raise ValueError("Callback hostname has no addresses")
    for address in ips:
        # is_global also rejects shared CGNAT ranges that are neither private
        # nor public under the SDK's address categories.
        if not ipaddress.ip_address(address).is_global or not await validate_push_notification_url(
            str(url.copy_with(host=address, path="/", query=None))
        ):
            raise ValueError("Push notification URL is not public")
    return ips


async def validate_callback_url(url: str) -> bool:
    """Apply the SDK public-address policy within a bounded DNS lookup."""
    try:
        await asyncio.wait_for(_public_callback_addresses(httpx.URL(url)), timeout=CALLBACK_DNS_TIMEOUT)
        return True
    except (httpx.InvalidURL, TypeError, ValueError, OSError, asyncio.TimeoutError):
        return False


class PublicWebhookTransport(httpx.AsyncBaseTransport):
    """Pin callback connections to validated public addresses.

    The SDK URL validator is also applied when registering a callback. Resolve
    again immediately before dispatch, validate every returned address, then
    connect to a numeric IP so DNS cannot change between checking and dialing.
    Host and TLS certificate/SNI verification retain the original hostname.
    """

    def __init__(self) -> None:
        # Never share a connection across hostnames that happen to share an IP.
        self._transport = httpx.AsyncHTTPTransport(trust_env=False, limits=httpx.Limits(max_keepalive_connections=0))

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        try:
            ips = await asyncio.wait_for(_public_callback_addresses(url), timeout=CALLBACK_DNS_TIMEOUT)
        except asyncio.TimeoutError as error:
            raise httpx.ConnectTimeout("Push notification DNS lookup timed out", request=request) from error
        except (OSError, ValueError) as error:
            raise httpx.ConnectError(str(error), request=request) from error
        headers = httpx.Headers(request.headers)
        headers["Host"] = url.netloc.decode("ascii")
        pinned_request = httpx.Request(
            request.method,
            url.copy_with(host=ips[0]),
            headers=headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": url.raw_host.decode("ascii")},
        )
        return await self._transport.handle_async_request(pinned_request)

    async def aclose(self) -> None:
        await self._transport.aclose()


class _PushHttpClient(httpx.AsyncClient):
    def __init__(self):
        self._callback_transport = PublicWebhookTransport()
        super().__init__(transport=self._callback_transport, timeout=10.0, follow_redirects=False, trust_env=False)

    async def post_callback(self, url, *, json, headers):
        # HTTPX's normal request path logs the complete URL at INFO. Use its
        # documented transport API so query credentials never reach that log.
        request = self.build_request("POST", url, json=json, headers=headers)
        response = await self._callback_transport.handle_async_request(request)
        try:
            return response.is_success
        finally:
            await response.aclose()


def create_push_http_client() -> _PushHttpClient:
    """Create a callback client without redirects or environment proxies."""
    return _PushHttpClient()


class ProtocolPushSender(BasePushNotificationSender):
    """Keep SDK event/config handling with protocol media and secret-safe logs."""

    async def _dispatch_notification(self, event, push_info, task_id):
        try:
            return await asyncio.wait_for(self._deliver(event, push_info), timeout=CALLBACK_DELIVERY_TIMEOUT)
        except Exception:
            # Exception text/tracebacks can include URLs, query credentials,
            # request headers or response bodies controlled by the callback.
            logger.warning("Push notification delivery failed")
            return False

    async def _deliver(self, event, push_info):
        if self._push_url_validator and not await self._push_url_validator(push_info.url):
            return False
        headers = {"Content-Type": "application/a2a+json"}
        if push_info.token:
            headers["X-A2A-Notification-Token"] = push_info.token
        auth = push_info.authentication
        if auth.scheme and auth.credentials:
            headers["Authorization"] = f"{auth.scheme} {auth.credentials}"
        return await self._client.post_callback(
            push_info.url, json=MessageToDict(to_stream_response(event)), headers=headers
        )


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
    async def notify(self, event: dict[str, Any]) -> None:
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
        secret: str | None = None,
        headers: dict[str, str] | None = None,
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

    async def notify(self, event: dict[str, Any]) -> None:
        """Send the event to the configured webhook URL with retries."""
        try:
            import httpx
        except ImportError:
            logger.error("httpx is required for WebhookPushNotifier. Install it with: pip install httpx")
            return

        payload = json.dumps(event, default=str)
        headers = {
            "Content-Type": "application/json",
            "X-A2A-Event": event.get("skill", "unknown"),
            **self.headers,
        }

        if self.secret:
            headers["X-A2A-Signature"] = f"sha256={self._sign_payload(payload)}"

        last_error: Exception | None = None
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
                    wait = 2**attempt  # 1s, 2s, 4s
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

    async def notify(self, event: dict[str, Any]) -> None:
        log_fn = getattr(logger, self.level.lower(), logger.info)
        log_fn(
            "[A2A Push] skill=%s status=%s timestamp=%s",
            event.get("skill"),
            event.get("status"),
            event.get("timestamp"),
        )
