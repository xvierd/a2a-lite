"""
Tests for per-task push notifications: TaskPushRegistry,
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
from a2a_lite.push_notifications import TaskPushRegistry

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
                "taskId": "task-42",
                "id": "task-42",
                "url": "http://hook.test/cb",
                "token": None,
            },
        }
        mock_client = _mock_httpx_response(response_data)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await set_task_push_notification(
                "http://agent:8787",
                "task-42",
                "http://hook.test/cb",
            )
            assert result["taskId"] == "task-42"
            assert result["url"] == "http://hook.test/cb"

            # Verify the JSON-RPC body
            call_args = mock_client.post.call_args
            body = call_args[1]["json"]
            assert body["method"] == "CreateTaskPushNotificationConfig"
            assert body["params"]["taskId"] == "task-42"
            assert body["params"]["url"] == "http://hook.test/cb"


class TestGetTaskPushNotification:
    @pytest.mark.asyncio
    async def test_get_task_push_notification(self):
        response_data = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {
                "taskId": "task-42",
                "id": "task-42",
                "url": "http://hook.test/cb",
                "token": "secret",
            },
        }
        mock_client = _mock_httpx_response(response_data)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await get_task_push_notification("http://agent:8787", "task-42")
            assert result["taskId"] == "task-42"
            assert result["url"] == "http://hook.test/cb"

            body = mock_client.post.call_args[1]["json"]
            assert body["method"] == "GetTaskPushNotificationConfig"
            assert body["params"]["taskId"] == "task-42"


class TestDeleteTaskPushNotification:
    @pytest.mark.asyncio
    async def test_delete_task_push_notification(self):
        response_data = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {},
        }
        mock_client = _mock_httpx_response(response_data)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await delete_task_push_notification("http://agent:8787", "task-42")
            assert result == {}

            body = mock_client.post.call_args[1]["json"]
            assert body["method"] == "DeleteTaskPushNotificationConfig"
            assert body["params"]["taskId"] == "task-42"


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
            mock.return_value = {"taskId": "task-99", "url": "http://hook/cb", "token": None}
            result = await handle.subscribe("http://hook/cb")
            assert result["taskId"] == "task-99"
            mock.assert_called_once_with("http://agent:8787", "task-99", "http://hook/cb", None, 10.0)

    @pytest.mark.asyncio
    async def test_task_handle_unsubscribe(self):
        handle = TaskHandle(task_id="task-99", result="ok", _agent_url="http://agent:8787")

        with patch(
            "a2a_lite.orchestration.delete_task_push_notification",
            new_callable=AsyncMock,
        ) as mock:
            mock.return_value = {}
            result = await handle.unsubscribe()
            assert result == {}
            mock.assert_called_once_with("http://agent:8787", "task-99", 10.0)

    @pytest.mark.asyncio
    async def test_task_handle_get_push_config(self):
        handle = TaskHandle(task_id="task-99", result="ok", _agent_url="http://agent:8787")

        with patch(
            "a2a_lite.orchestration.get_task_push_notification",
            new_callable=AsyncMock,
        ) as mock:
            mock.return_value = {
                "taskId": "task-99",
                "url": "http://hook/cb",
                "token": "tok",
            }
            result = await handle.get_push_config()
            assert result["url"] == "http://hook/cb"
            mock.assert_called_once_with("http://agent:8787", "task-99", 10.0)
