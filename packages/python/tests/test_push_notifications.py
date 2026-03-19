"""
Tests for push_notifications module and Agent push_notifier / protocol_task_store wiring.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from a2a_lite.push_notifications import LogPushNotifier, PushNotifier, WebhookPushNotifier

# ---------------------------------------------------------------------------
# LogPushNotifier
# ---------------------------------------------------------------------------


class TestLogPushNotifier:
    """Tests for LogPushNotifier."""

    @pytest.mark.asyncio
    async def test_notify_logs_event(self, caplog):
        """notify() should log the event and not raise."""
        notifier = LogPushNotifier()
        event = {"skill": "greet", "result": "Hello"}

        with caplog.at_level(logging.INFO, logger="a2a_lite.push_notifications"):
            await notifier.notify(event)

        assert any("greet" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_notify_does_not_raise(self):
        """notify() must not raise even with unusual payloads."""
        notifier = LogPushNotifier()
        await notifier.notify({})
        await notifier.notify({"nested": {"a": 1}, "list": [1, 2, 3]})

    @pytest.mark.asyncio
    async def test_notify_custom_log_level(self, caplog):
        """LogPushNotifier respects a custom log level."""
        notifier = LogPushNotifier(level="DEBUG")
        with caplog.at_level(logging.DEBUG, logger="a2a_lite.push_notifications"):
            await notifier.notify({"x": 1})
        assert any(r.levelno == logging.DEBUG for r in caplog.records)

    def test_is_abstract_subclass(self):
        """LogPushNotifier must be a subclass of PushNotifier."""
        assert issubclass(LogPushNotifier, PushNotifier)


# ---------------------------------------------------------------------------
# WebhookPushNotifier — helpers
# ---------------------------------------------------------------------------


def _make_response(status_code: int) -> MagicMock:
    """Return a mock httpx Response object."""
    import httpx

    resp = MagicMock()
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status_code), request=MagicMock(), response=MagicMock()
        )
    else:
        resp.raise_for_status = MagicMock()  # no-op
    return resp


def _verify_signature(body: bytes | str, secret: str, header_value: str) -> bool:
    """Verify an HMAC-SHA256 signature matches the header value."""
    if isinstance(body, str):
        body = body.encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return header_value == f"sha256={expected}"


# ---------------------------------------------------------------------------
# WebhookPushNotifier
# ---------------------------------------------------------------------------


class TestWebhookPushNotifier:
    """Tests for WebhookPushNotifier."""

    @pytest.mark.asyncio
    async def test_posts_to_webhook_url(self):
        """notify() should POST to the configured URL."""
        mock_response = _make_response(200)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        notifier = WebhookPushNotifier(url="https://hooks.example.com/events")

        with patch("httpx.AsyncClient", return_value=mock_client):
            await notifier.notify({"skill": "greet", "result": "Hello"})

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs.args[0] == "https://hooks.example.com/events"

    @pytest.mark.asyncio
    async def test_content_type_header(self):
        """notify() should include Content-Type: application/json."""
        mock_response = _make_response(200)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        notifier = WebhookPushNotifier(url="https://hooks.example.com/events")

        with patch("httpx.AsyncClient", return_value=mock_client):
            await notifier.notify({"skill": "test"})

        _, kwargs = mock_client.post.call_args
        headers = kwargs.get("headers", {})
        assert headers.get("Content-Type") == "application/json"

    @pytest.mark.asyncio
    async def test_hmac_signature_header_present(self):
        """When secret is set, an X-A2A-Signature header should be included."""
        mock_response = _make_response(200)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        secret = "my-super-secret"
        notifier = WebhookPushNotifier(url="https://hooks.example.com/events", secret=secret)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await notifier.notify({"skill": "greet"})

        _, kwargs = mock_client.post.call_args
        headers = kwargs.get("headers", {})
        assert "X-A2A-Signature" in headers
        assert headers["X-A2A-Signature"].startswith("sha256=")

    @pytest.mark.asyncio
    async def test_hmac_signature_is_valid(self):
        """The HMAC signature in the header must be verifiable against the body."""
        secret = "verify-me"
        captured_calls: list[dict] = []

        mock_response = _make_response(200)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        async def _capture_post(url, *, content, headers, **_kw):
            captured_calls.append({"body": content, "headers": headers})
            return mock_response

        mock_client.post = _capture_post

        notifier = WebhookPushNotifier(url="https://hooks.example.com/events", secret=secret)
        event = {"skill": "calculate", "result": 42}

        with patch("httpx.AsyncClient", return_value=mock_client):
            await notifier.notify(event)

        assert len(captured_calls) == 1
        body = captured_calls[0]["body"]
        sig_header = captured_calls[0]["headers"]["X-A2A-Signature"]

        assert _verify_signature(body, secret, sig_header)

    @pytest.mark.asyncio
    async def test_no_signature_header_without_secret(self):
        """Without a secret, no X-A2A-Signature header should be sent."""
        mock_response = _make_response(200)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        notifier = WebhookPushNotifier(url="https://hooks.example.com/events")

        with patch("httpx.AsyncClient", return_value=mock_client):
            await notifier.notify({"skill": "greet"})

        _, kwargs = mock_client.post.call_args
        headers = kwargs.get("headers", {})
        assert "X-A2A-Signature" not in headers

    @pytest.mark.asyncio
    async def test_returns_successfully_on_2xx(self):
        """notify() should not raise on 2xx responses."""
        for status in (200, 201, 204):
            mock_response = _make_response(status)
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)

            notifier = WebhookPushNotifier(url="https://hooks.example.com/events", max_retries=1)

            with patch("httpx.AsyncClient", return_value=mock_client):
                await notifier.notify({"skill": "greet"})  # should not raise

    @pytest.mark.asyncio
    async def test_logs_error_on_4xx_after_retries(self, caplog):
        """notify() should log an error after exhausting retries on 4xx responses."""
        import httpx

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "400", request=MagicMock(), response=MagicMock()
        )
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        notifier = WebhookPushNotifier(url="https://hooks.example.com/events", max_retries=1)

        with caplog.at_level(logging.ERROR, logger="a2a_lite.push_notifications"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                await notifier.notify({"skill": "greet"})  # should not raise

        assert any("failed" in r.message.lower() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_logs_error_on_5xx_after_retries(self, caplog):
        """notify() should log an error after exhausting retries on 5xx responses."""
        import httpx

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "503", request=MagicMock(), response=MagicMock()
        )
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        notifier = WebhookPushNotifier(url="https://hooks.example.com/events", max_retries=1)

        with caplog.at_level(logging.ERROR, logger="a2a_lite.push_notifications"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                await notifier.notify({"skill": "greet"})  # should not raise

        assert any("failed" in r.message.lower() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_retries_on_failure_then_succeeds(self):
        """notify() should retry and succeed when first attempt fails."""
        import httpx

        ok_response = MagicMock()
        ok_response.raise_for_status = MagicMock()  # no-op, 2xx

        fail_response = MagicMock()
        fail_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )

        call_count = 0
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        async def _flaky_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return fail_response
            return ok_response

        mock_client.post = _flaky_post

        notifier = WebhookPushNotifier(
            url="https://hooks.example.com/events",
            max_retries=2,  # 2 total attempts, first fails, second succeeds
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("httpx.AsyncClient", return_value=mock_client):
                await notifier.notify({"skill": "greet"})  # should not raise

        assert call_count == 2  # first attempt failed, second succeeded

    @pytest.mark.asyncio
    async def test_retries_on_network_exception(self):
        """notify() should retry on transport-level exceptions."""
        import httpx

        call_count = 0
        ok_response = MagicMock()
        ok_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        async def _flaky_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("connection refused")
            return ok_response

        mock_client.post = _flaky_post

        notifier = WebhookPushNotifier(
            url="https://hooks.example.com/events",
            max_retries=2,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("httpx.AsyncClient", return_value=mock_client):
                await notifier.notify({"skill": "greet"})

        assert call_count == 2

    def test_secret_stored_as_str(self):
        """WebhookPushNotifier stores the secret as provided."""
        notifier = WebhookPushNotifier(
            url="https://hooks.example.com/events",
            secret="my-secret",
        )
        assert notifier.secret == "my-secret"

    def test_no_secret_by_default(self):
        """WebhookPushNotifier has no secret by default."""
        notifier = WebhookPushNotifier(url="https://hooks.example.com/events")
        assert notifier.secret is None

    def test_is_abstract_subclass(self):
        """WebhookPushNotifier must be a subclass of PushNotifier."""
        assert issubclass(WebhookPushNotifier, PushNotifier)


# ---------------------------------------------------------------------------
# Agent.protocol_task_store wiring
# ---------------------------------------------------------------------------


class TestProtocolTaskStoreWiring:
    """Tests that Agent passes protocol_task_store to DefaultRequestHandler."""

    def test_protocol_task_store_defaults_to_in_memory(self):
        """When protocol_task_store is None, _build_app creates an InMemoryTaskStore."""
        from a2a.server.tasks import InMemoryTaskStore

        from a2a_lite import Agent

        agent = Agent(name="Test", description="Test")

        @agent.skill("ping")
        async def ping() -> str:
            return "pong"

        # Verify the app builds without error (uses default InMemoryTaskStore)
        with patch("a2a_lite.agent.DefaultRequestHandler") as mock_handler_cls:
            mock_handler_cls.return_value = MagicMock()
            agent._build_app("localhost", 8787)

        _, kwargs = mock_handler_cls.call_args
        assert isinstance(kwargs["task_store"], InMemoryTaskStore)

    def test_custom_protocol_task_store_passed_through(self):
        """When protocol_task_store is set, it is passed to DefaultRequestHandler."""
        from a2a.server.tasks import InMemoryTaskStore

        from a2a_lite import Agent

        custom_store = InMemoryTaskStore()
        agent = Agent(name="Test", description="Test", protocol_task_store=custom_store)

        @agent.skill("ping")
        async def ping() -> str:
            return "pong"

        with patch("a2a_lite.agent.DefaultRequestHandler") as mock_handler_cls:
            mock_handler_cls.return_value = MagicMock()
            agent._build_app("localhost", 8787)

        _, kwargs = mock_handler_cls.call_args
        assert kwargs["task_store"] is custom_store


# ---------------------------------------------------------------------------
# Agent.push_notifier auto-wiring
# ---------------------------------------------------------------------------


class TestPushNotifierWiring:
    """Tests that Agent wires push_notifier into the on_complete callback list."""

    @pytest.mark.asyncio
    async def test_push_notifier_called_on_complete(self):
        """When push_notifier is set, it is invoked after a skill completes."""
        from a2a_lite import Agent
        from a2a_lite.executor import LiteAgentExecutor

        notified_events: list[dict[str, Any]] = []

        class CapturingNotifier(PushNotifier):
            async def notify(self, event: dict[str, Any]) -> None:
                notified_events.append(event)

        agent = Agent(
            name="Test",
            description="Test",
            push_notifier=CapturingNotifier(),
        )

        @agent.skill("greet")
        async def greet(name: str) -> str:
            return f"Hello, {name}"

        # Capture the executor built by _build_app
        captured_executors: list[LiteAgentExecutor] = []
        original_build = LiteAgentExecutor.__init__

        def _capture_init(self_inner, *args, **kwargs):
            original_build(self_inner, *args, **kwargs)
            captured_executors.append(self_inner)

        with patch("a2a_lite.agent.DefaultRequestHandler", return_value=MagicMock()):
            with patch.object(LiteAgentExecutor, "__init__", _capture_init):
                agent._build_app("localhost", 8787)

        assert len(captured_executors) == 1
        executor = captured_executors[0]

        # The push_notifier wrapper should be the first on_complete handler
        assert len(executor.on_complete) >= 1

        # Simulate the on_complete call
        for hook in executor.on_complete:
            import asyncio

            if asyncio.iscoroutinefunction(hook):
                await hook("greet", "Hello, World", MagicMock())
            else:
                hook("greet", "Hello, World", MagicMock())

        assert len(notified_events) == 1
        assert notified_events[0]["skill"] == "greet"

    def test_no_push_notifier_on_complete_unchanged(self):
        """When push_notifier is None, on_complete list is not modified."""
        from a2a_lite import Agent
        from a2a_lite.executor import LiteAgentExecutor

        agent = Agent(name="Test", description="Test")

        @agent.skill("ping")
        async def ping() -> str:
            return "pong"

        extra_called = []

        @agent.on_complete
        async def my_hook(skill, result, ctx):
            extra_called.append(skill)

        captured_executors: list[LiteAgentExecutor] = []
        original_build = LiteAgentExecutor.__init__

        def _capture_init(self_inner, *args, **kwargs):
            original_build(self_inner, *args, **kwargs)
            captured_executors.append(self_inner)

        with patch("a2a_lite.agent.DefaultRequestHandler", return_value=MagicMock()):
            with patch.object(LiteAgentExecutor, "__init__", _capture_init):
                agent._build_app("localhost", 8787)

        executor = captured_executors[0]
        # Only the user-registered hook, no extra wrapper
        assert len(executor.on_complete) == 1

    @pytest.mark.asyncio
    async def test_push_notifier_error_does_not_propagate(self):
        """If push_notifier.notify() raises, the error should be swallowed."""
        from a2a_lite import Agent
        from a2a_lite.executor import LiteAgentExecutor

        class BrokenNotifier(PushNotifier):
            async def notify(self, event: dict[str, Any]) -> None:
                raise RuntimeError("network down")

        agent = Agent(
            name="Test",
            description="Test",
            push_notifier=BrokenNotifier(),
        )

        @agent.skill("ping")
        async def ping() -> str:
            return "pong"

        captured_executors: list[LiteAgentExecutor] = []
        original_build = LiteAgentExecutor.__init__

        def _capture_init(self_inner, *args, **kwargs):
            original_build(self_inner, *args, **kwargs)
            captured_executors.append(self_inner)

        with patch("a2a_lite.agent.DefaultRequestHandler", return_value=MagicMock()):
            with patch.object(LiteAgentExecutor, "__init__", _capture_init):
                agent._build_app("localhost", 8787)

        executor = captured_executors[0]

        # Should not raise even though notifier throws
        import asyncio

        for hook in executor.on_complete:
            if asyncio.iscoroutinefunction(hook):
                await hook("ping", "pong", MagicMock())
            else:
                hook("ping", "pong", MagicMock())
