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
    from a2a_lite.push_notifications import TaskPushRegistry

    # Server-side: registry is auto-created on every Agent.
    # Client-side: use set_task_push_notification() or handle.subscribe().
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-task push notification registry & middleware
# ---------------------------------------------------------------------------


class TaskPushRegistry:
    """
    Server-side registry mapping task IDs to webhook configurations.
    Used to deliver per-task push notifications when tasks complete.
    """

    def __init__(self) -> None:
        self._configs: dict[str, dict] = {}  # task_id -> {url, token}

    def set(self, task_id: str, url: str, token: str | None = None) -> None:
        self._configs[task_id] = {"url": url, "token": token}

    def get(self, task_id: str) -> dict | None:
        return self._configs.get(task_id)

    def delete(self, task_id: str) -> bool:
        return self._configs.pop(task_id, None) is not None

    def __contains__(self, task_id: str) -> bool:
        return task_id in self._configs


class PushNotificationMiddleware:
    """
    Starlette ASGI middleware that handles the A2A v1.0 push notification
    JSON-RPC methods (CreateTaskPushNotificationConfig, GetTaskPushNotificationConfig,
    DeleteTaskPushNotificationConfig).
    Wraps the underlying A2A SDK app and intercepts these specific methods.
    """

    def __init__(self, app: Any, registry: TaskPushRegistry) -> None:
        self.app = app
        self.registry = registry

    def __getattr__(self, name: str) -> Any:
        # Proxy attribute access to the wrapped app so callers can still
        # inspect Starlette-specific attributes (e.g. ``routes``).
        return getattr(self.app, name)

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return

        # Buffer the request body so we can read it and also replay it
        body_parts: list[bytes] = []
        more_body = True
        while more_body:
            message = await receive()
            body_parts.append(message.get("body", b""))
            more_body = message.get("more_body", False)
        body = b"".join(body_parts)

        try:
            data = json.loads(body)
            method = data.get("method", "")
        except (json.JSONDecodeError, AttributeError):
            method = ""

        if method == "CreateTaskPushNotificationConfig":
            await self._handle_set(data, send)
        elif method == "GetTaskPushNotificationConfig":
            await self._handle_get(data, send)
        elif method == "DeleteTaskPushNotificationConfig":
            await self._handle_delete(data, send)
        else:
            # Not a push notification method -- replay body to original app
            replayed = False

            async def replay_receive() -> dict:
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": body, "more_body": False}
                # Pass through so SSE responses can still detect real disconnects
                return await receive()

            await self.app(scope, replay_receive, send)

    async def _send_json(self, send: Any, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def _handle_set(self, data: dict, send: Any) -> None:
        params = data.get("params", {})
        task_id = params.get("taskId", "")
        config_id = params.get("id") or task_id
        url = params.get("url", "")
        token = params.get("token")
        if not task_id or not url:
            await self._send_json(
                send,
                {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "error": {"code": -32602, "message": "Missing required fields: taskId and url"},
                },
            )
            return
        self.registry.set(task_id, url, token)
        await self._send_json(
            send,
            {
                "jsonrpc": "2.0",
                "id": data.get("id"),
                "result": {"taskId": task_id, "id": config_id, "url": url, "token": token},
            },
        )

    async def _handle_get(self, data: dict, send: Any) -> None:
        params = data.get("params", {})
        task_id = params.get("taskId", "")
        config_id = params.get("id") or task_id
        config = self.registry.get(task_id)
        if config is None:
            await self._send_json(
                send,
                {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "error": {"code": -32001, "message": f"No push notification config for task {task_id}"},
                },
            )
            return
        await self._send_json(
            send,
            {
                "jsonrpc": "2.0",
                "id": data.get("id"),
                "result": {"taskId": task_id, "id": config_id, "url": config["url"], "token": config["token"]},
            },
        )

    async def _handle_delete(self, data: dict, send: Any) -> None:
        params = data.get("params", {})
        task_id = params.get("taskId", "")
        self.registry.delete(task_id)
        await self._send_json(
            send,
            {
                "jsonrpc": "2.0",
                "id": data.get("id"),
                "result": {},
            },
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
