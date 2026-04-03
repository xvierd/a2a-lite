"""
Tests for per-task push notifications: TaskPushRegistry, PushNotificationMiddleware,
client-side functions, and TaskHandle methods.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from a2a_lite.orchestration import (
    TaskHandle,
    delete_task_push_notification,
    get_task_push_notification,
    set_task_push_notification,
)
from a2a_lite.push_notifications import PushNotificationMiddleware, TaskPushRegistry

# ---------------------------------------------------------------------------
# TaskPushRegistry
# ---------------------------------------------------------------------------


class TestTaskPushRegistry:
    def test_registry_set_get(self):
        reg = TaskPushRegistry()
        reg.set("task-1", "http://hook.test/cb", "tok-abc")
        config = reg.get("task-1")
        assert config == {"url": "http://hook.test/cb", "token": "tok-abc"}

    def test_registry_delete(self):
        reg = TaskPushRegistry()
        reg.set("task-1", "http://hook.test/cb")
        assert reg.delete("task-1") is True
        assert reg.get("task-1") is None

    def test_registry_contains(self):
        reg = TaskPushRegistry()
        reg.set("task-1", "http://hook.test/cb")
        assert "task-1" in reg
        assert "task-2" not in reg

    def test_registry_get_missing(self):
        reg = TaskPushRegistry()
        assert reg.get("nonexistent") is None

    def test_registry_delete_missing(self):
        reg = TaskPushRegistry()
        assert reg.delete("nonexistent") is False

    def test_registry_set_no_token(self):
        reg = TaskPushRegistry()
        reg.set("task-1", "http://hook.test/cb")
        config = reg.get("task-1")
        assert config == {"url": "http://hook.test/cb", "token": None}


# ---------------------------------------------------------------------------
# PushNotificationMiddleware (ASGI-level)
# ---------------------------------------------------------------------------


async def _asgi_send_collect(messages: list):
    """Returns an ASGI send callable that collects sent messages."""

    async def send(message):
        messages.append(message)

    return send


async def _run_middleware(registry, body_dict):
    """Helper: run the middleware with a JSON body and return (status, response_dict)."""
    mw = PushNotificationMiddleware(app=None, registry=registry)

    body = json.dumps(body_dict).encode()
    scope = {"type": "http", "method": "POST", "path": "/"}

    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(msg):
        sent.append(msg)

    await mw(scope, receive, send)

    status = sent[0]["status"]
    resp_body = json.loads(sent[1]["body"])
    return status, resp_body


class TestPushNotificationMiddleware:
    @pytest.mark.asyncio
    async def test_middleware_set(self):
        reg = TaskPushRegistry()
        status, resp = await _run_middleware(
            reg,
            {
                "jsonrpc": "2.0",
                "id": "req-1",
                "method": "tasks/pushNotification/set",
                "params": {
                    "id": "task-42",
                    "pushNotificationConfig": {"url": "http://hook.test/cb", "token": "secret"},
                },
            },
        )
        assert status == 200
        assert resp["result"]["id"] == "task-42"
        assert resp["result"]["pushNotificationConfig"]["url"] == "http://hook.test/cb"
        # Verify it's actually in the registry
        assert "task-42" in reg
        assert reg.get("task-42")["url"] == "http://hook.test/cb"

    @pytest.mark.asyncio
    async def test_middleware_get(self):
        reg = TaskPushRegistry()
        reg.set("task-42", "http://hook.test/cb", "secret")
        status, resp = await _run_middleware(
            reg,
            {
                "jsonrpc": "2.0",
                "id": "req-2",
                "method": "tasks/pushNotification/get",
                "params": {"id": "task-42"},
            },
        )
        assert status == 200
        assert resp["result"]["pushNotificationConfig"]["url"] == "http://hook.test/cb"

    @pytest.mark.asyncio
    async def test_middleware_delete(self):
        reg = TaskPushRegistry()
        reg.set("task-42", "http://hook.test/cb")
        status, resp = await _run_middleware(
            reg,
            {
                "jsonrpc": "2.0",
                "id": "req-3",
                "method": "tasks/pushNotification/delete",
                "params": {"id": "task-42"},
            },
        )
        assert status == 200
        assert resp["result"]["id"] == "task-42"
        assert "task-42" not in reg

    @pytest.mark.asyncio
    async def test_middleware_passthrough(self):
        """Non-push methods pass through to the wrapped app."""
        reg = TaskPushRegistry()
        inner_called = False

        async def inner_app(scope, receive, send):
            nonlocal inner_called
            inner_called = True
            # Read the replayed body
            msg = await receive()
            body = json.loads(msg["body"])
            assert body["method"] == "message/send"
            # Send a response
            resp = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {}}).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": resp})

        mw = PushNotificationMiddleware(app=inner_app, registry=reg)

        body = json.dumps({"jsonrpc": "2.0", "id": "req-x", "method": "message/send", "params": {}}).encode()
        scope = {"type": "http", "method": "POST", "path": "/"}

        sent: list[dict] = []

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(msg):
            sent.append(msg)

        await mw(scope, receive, send)
        assert inner_called

    @pytest.mark.asyncio
    async def test_middleware_missing_params(self):
        """Missing id or url returns a JSON-RPC error."""
        reg = TaskPushRegistry()
        status, resp = await _run_middleware(
            reg,
            {
                "jsonrpc": "2.0",
                "id": "req-err",
                "method": "tasks/pushNotification/set",
                "params": {"id": "task-1", "pushNotificationConfig": {}},
            },
        )
        assert status == 200
        assert "error" in resp
        assert resp["error"]["code"] == -32602

    @pytest.mark.asyncio
    async def test_middleware_get_missing_task(self):
        """Getting config for unknown task returns error."""
        reg = TaskPushRegistry()
        status, resp = await _run_middleware(
            reg,
            {
                "jsonrpc": "2.0",
                "id": "req-miss",
                "method": "tasks/pushNotification/get",
                "params": {"id": "nonexistent"},
            },
        )
        assert status == 200
        assert "error" in resp
        assert resp["error"]["code"] == -32001

    @pytest.mark.asyncio
    async def test_middleware_non_http_passthrough(self):
        """Non-HTTP scopes pass through directly."""
        inner_called = False

        async def inner_app(scope, receive, send):
            nonlocal inner_called
            inner_called = True

        reg = TaskPushRegistry()
        mw = PushNotificationMiddleware(app=inner_app, registry=reg)

        await mw({"type": "websocket"}, None, None)
        assert inner_called

    @pytest.mark.asyncio
    async def test_middleware_non_post_passthrough(self):
        """Non-POST HTTP requests pass through directly."""
        inner_called = False

        async def inner_app(scope, receive, send):
            nonlocal inner_called
            inner_called = True

        reg = TaskPushRegistry()
        mw = PushNotificationMiddleware(app=inner_app, registry=reg)

        await mw({"type": "http", "method": "GET"}, None, None)
        assert inner_called


# ---------------------------------------------------------------------------
# Client-side functions
# ---------------------------------------------------------------------------


def _mock_httpx_response(response_data: dict):
    """Build a patch context for httpx.AsyncClient that returns the given data."""
    mock_response = MagicMock()
    mock_response.json.return_value = response_data
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    return mock_client


class TestSetTaskPushNotification:
    @pytest.mark.asyncio
    async def test_set_task_push_notification(self):
        response_data = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {
                "id": "task-42",
                "pushNotificationConfig": {"url": "http://hook.test/cb", "token": None},
            },
        }
        mock_client = _mock_httpx_response(response_data)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await set_task_push_notification(
                "http://agent:8787",
                "task-42",
                "http://hook.test/cb",
            )
            assert result["id"] == "task-42"
            assert result["pushNotificationConfig"]["url"] == "http://hook.test/cb"

            # Verify the JSON-RPC body
            call_args = mock_client.post.call_args
            body = call_args[1]["json"]
            assert body["method"] == "tasks/pushNotification/set"
            assert body["params"]["id"] == "task-42"
            assert body["params"]["pushNotificationConfig"]["url"] == "http://hook.test/cb"


class TestGetTaskPushNotification:
    @pytest.mark.asyncio
    async def test_get_task_push_notification(self):
        response_data = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {
                "id": "task-42",
                "pushNotificationConfig": {"url": "http://hook.test/cb", "token": "secret"},
            },
        }
        mock_client = _mock_httpx_response(response_data)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await get_task_push_notification("http://agent:8787", "task-42")
            assert result["id"] == "task-42"
            assert result["pushNotificationConfig"]["url"] == "http://hook.test/cb"

            body = mock_client.post.call_args[1]["json"]
            assert body["method"] == "tasks/pushNotification/get"
            assert body["params"]["id"] == "task-42"


class TestDeleteTaskPushNotification:
    @pytest.mark.asyncio
    async def test_delete_task_push_notification(self):
        response_data = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {"id": "task-42"},
        }
        mock_client = _mock_httpx_response(response_data)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await delete_task_push_notification("http://agent:8787", "task-42")
            assert result["id"] == "task-42"

            body = mock_client.post.call_args[1]["json"]
            assert body["method"] == "tasks/pushNotification/delete"
            assert body["params"]["id"] == "task-42"


# ---------------------------------------------------------------------------
# TaskHandle methods
# ---------------------------------------------------------------------------


class TestTaskHandleSubscribe:
    @pytest.mark.asyncio
    async def test_task_handle_subscribe(self):
        handle = TaskHandle(task_id="task-99", result="ok", _agent_url="http://agent:8787")

        with patch(
            "a2a_lite.orchestration.set_task_push_notification",
            new_callable=AsyncMock,
        ) as mock:
            mock.return_value = {"id": "task-99", "pushNotificationConfig": {"url": "http://hook/cb", "token": None}}
            result = await handle.subscribe("http://hook/cb")
            assert result["id"] == "task-99"
            mock.assert_called_once_with("http://agent:8787", "task-99", "http://hook/cb", None, 10.0)

    @pytest.mark.asyncio
    async def test_task_handle_unsubscribe(self):
        handle = TaskHandle(task_id="task-99", result="ok", _agent_url="http://agent:8787")

        with patch(
            "a2a_lite.orchestration.delete_task_push_notification",
            new_callable=AsyncMock,
        ) as mock:
            mock.return_value = {"id": "task-99"}
            result = await handle.unsubscribe()
            assert result["id"] == "task-99"
            mock.assert_called_once_with("http://agent:8787", "task-99", 10.0)

    @pytest.mark.asyncio
    async def test_task_handle_get_push_config(self):
        handle = TaskHandle(task_id="task-99", result="ok", _agent_url="http://agent:8787")

        with patch(
            "a2a_lite.orchestration.get_task_push_notification",
            new_callable=AsyncMock,
        ) as mock:
            mock.return_value = {
                "id": "task-99",
                "pushNotificationConfig": {"url": "http://hook/cb", "token": "tok"},
            }
            result = await handle.get_push_config()
            assert result["pushNotificationConfig"]["url"] == "http://hook/cb"
            mock.assert_called_once_with("http://agent:8787", "task-99", 10.0)
