"""
Tests for the orchestration module (AgentNetwork, delegate).
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from a2a_lite import Agent
from a2a_lite.orchestration import (
    AgentCardInfo,
    AgentNetwork,
    TaskHandle,
    _call_remote_skill,
    _extract_result,
    cancel_remote_task,
    discover,
    get_remote_task,
    stream_remote_skill,
)


class TestAgentNetwork:
    def test_create_empty(self):
        net = AgentNetwork()
        assert len(net) == 0

    def test_create_with_agents(self):
        net = AgentNetwork(agents={"a": "http://a:8787", "b": "http://b:8787"})
        assert len(net) == 2
        assert "a" in net
        assert "b" in net

    def test_add_and_get(self):
        net = AgentNetwork()
        net.add("weather", "http://weather:8787")
        assert net.get("weather") == "http://weather:8787"

    def test_get_nonexistent(self):
        net = AgentNetwork()
        assert net.get("missing") is None

    def test_remove(self):
        net = AgentNetwork()
        net.add("a", "http://a:8787")
        assert net.remove("a") is True
        assert "a" not in net

    def test_remove_nonexistent(self):
        net = AgentNetwork()
        assert net.remove("missing") is False

    def test_list(self):
        net = AgentNetwork()
        net.add("a", "http://a:8787")
        net.add("b", "http://b:8787")
        result = net.list()
        assert result == {"a": "http://a:8787", "b": "http://b:8787"}

    def test_contains(self):
        net = AgentNetwork()
        net.add("a", "http://a:8787")
        assert "a" in net
        assert "b" not in net

    def test_repr(self):
        net = AgentNetwork()
        net.add("a", "http://a:8787")
        assert "a" in repr(net)

    def test_url_trailing_slash_stripped(self):
        net = AgentNetwork()
        net.add("a", "http://a:8787/")
        assert net.get("a") == "http://a:8787"

    @pytest.mark.asyncio
    async def test_call_unknown_agent(self):
        net = AgentNetwork()
        with pytest.raises(KeyError, match="not found"):
            await net.call("missing", "skill")

    @pytest.mark.asyncio
    async def test_call_delegates(self):
        net = AgentNetwork()
        net.add("test", "http://test:8787")

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.return_value = ("hello", "task-123")
            result = await net.call("test", "greet", city="NYC")
            assert result == "hello"
            mock.assert_called_once_with("http://test:8787", "greet", {"city": "NYC"}, 30.0)

    @pytest.mark.asyncio
    async def test_broadcast(self):
        net = AgentNetwork()
        net.add("a", "http://a:8787")
        net.add("b", "http://b:8787")

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.side_effect = [("result_a", "tid-a"), ("result_b", "tid-b")]
            results = await net.broadcast("skill", x=1)
            assert results["a"] == "result_a"
            assert results["b"] == "result_b"

    @pytest.mark.asyncio
    async def test_broadcast_handles_errors(self):
        net = AgentNetwork()
        net.add("a", "http://a:8787")
        net.add("b", "http://b:8787")

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.side_effect = [("ok", "tid-a"), Exception("fail")]
            results = await net.broadcast("skill")
            assert results["a"] == "ok"
            assert "error" in results["b"]


class TestExtractResult:
    def test_extract_text_part(self):
        response = {"result": {"parts": [{"kind": "text", "text": '"hello"'}]}}
        assert _extract_result(response) == "hello"

    def test_extract_json_part(self):
        response = {"result": {"parts": [{"kind": "text", "text": '{"key": "value"}'}]}}
        assert _extract_result(response) == {"key": "value"}

    def test_extract_plain_text(self):
        response = {"result": {"parts": [{"kind": "text", "text": "just text"}]}}
        assert _extract_result(response) == "just text"

    def test_extract_error(self):
        from a2a_lite.errors import RemoteAgentError

        response = {"error": {"code": -32000, "message": "fail"}}
        with pytest.raises(RemoteAgentError) as exc_info:
            _extract_result(response)
        assert exc_info.value.response == response

    def test_extract_empty_result(self):
        response = {"result": {}}
        assert _extract_result(response) == {}

    def test_extract_type_text(self):
        response = {"result": {"parts": [{"type": "text", "text": "hello"}]}}
        assert _extract_result(response) == "hello"


class TestAgentDelegate:
    @pytest.mark.asyncio
    async def test_delegate_with_url(self):
        agent = Agent(name="Test", description="Test")

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.return_value = ("result", "task-123")
            result = await agent.delegate("http://other:8787", "skill", x=1)
            assert result == "result"

    @pytest.mark.asyncio
    async def test_delegate_with_network_name(self):
        net = AgentNetwork()
        net.add("other", "http://other:8787")
        agent = Agent(name="Test", description="Test", network=net)

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.return_value = ("result", "task-456")
            result = await agent.delegate("other", "skill", x=1)
            assert result == "result"
            mock.assert_called_once_with("http://other:8787", "skill", {"x": 1}, 30.0)

    @pytest.mark.asyncio
    async def test_delegate_unknown_name(self):
        net = AgentNetwork()
        agent = Agent(name="Test", description="Test", network=net)

        with pytest.raises(KeyError, match="not found"):
            await agent.delegate("missing", "skill")

    @pytest.mark.asyncio
    async def test_delegate_with_return_handle(self):
        agent = Agent(name="Test", description="Test")

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.return_value = ("result", "task-789")
            handle = await agent.delegate("http://other:8787", "skill", return_handle=True, x=1)
            assert isinstance(handle, TaskHandle)
            assert handle.task_id == "task-789"
            assert handle.result == "result"
            assert handle._agent_url == "http://other:8787"

    @pytest.mark.asyncio
    async def test_delegate_with_discover(self):
        agent = Agent(name="Test", description="Test")

        card = AgentCardInfo(
            name="Other",
            description="Other agent",
            url="http://other:8787",
            version="1.0.0",
            skills=[{"id": "skill", "name": "skill"}],
            supports_streaming=False,
            supports_push=False,
            raw={},
        )

        with (
            patch("a2a_lite.orchestration.discover", new_callable=AsyncMock, return_value=card) as mock_discover,
            patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock_call,
        ):
            mock_call.return_value = ("result", "task-abc")
            result = await agent.delegate("http://other:8787", "skill", discover=True, x=1)
            assert result == "result"
            mock_discover.assert_called_once()

    @pytest.mark.asyncio
    async def test_delegate_with_discover_skill_not_found(self):
        from a2a_lite.errors import SkillNotFoundError

        agent = Agent(name="Test", description="Test")

        card = AgentCardInfo(
            name="Other",
            description="Other agent",
            url="http://other:8787",
            version="1.0.0",
            skills=[{"id": "forecast", "name": "forecast"}],
            supports_streaming=False,
            supports_push=False,
            raw={},
        )

        with patch("a2a_lite.orchestration.discover", new_callable=AsyncMock, return_value=card):
            with pytest.raises(SkillNotFoundError):
                await agent.delegate("http://other:8787", "nonexistent_skill", discover=True)


class TestTaskHandle:
    def test_fields(self):
        handle = TaskHandle(task_id="abc123", result={"key": "value"}, _agent_url="http://test:8787")
        assert handle.task_id == "abc123"
        assert handle.result == {"key": "value"}
        assert handle._agent_url == "http://test:8787"

    def test_str(self):
        handle = TaskHandle(task_id="abc", result="hello world", _agent_url="http://test:8787")
        assert str(handle) == "hello world"

    def test_str_dict(self):
        handle = TaskHandle(task_id="abc", result={"key": "val"}, _agent_url="http://test:8787")
        assert str(handle) == "{'key': 'val'}"

    def test_repr(self):
        handle = TaskHandle(task_id="abc", result="hello", _agent_url="http://test:8787")
        r = repr(handle)
        assert "TaskHandle" in r
        assert "abc" in r
        assert "hello" in r


class TestTaskHandleLifecycleMethods:
    def test_agent_url_property(self):
        handle = TaskHandle(task_id="abc", result="ok", _agent_url="http://test:8787")
        assert handle.agent_url == "http://test:8787"

    @pytest.mark.asyncio
    async def test_get_status(self):
        handle = TaskHandle(task_id="task-xyz", result="ok", _agent_url="http://test:8787")

        with patch("a2a_lite.orchestration.get_remote_task", new_callable=AsyncMock) as mock:
            mock.return_value = {"id": "task-xyz", "status": {"state": "completed"}}
            result = await handle.get_status()
            assert isinstance(result, dict)
            assert result["status"]["state"] == "completed"
            mock.assert_called_once_with("http://test:8787", "task-xyz", 10.0)

    @pytest.mark.asyncio
    async def test_cancel(self):
        handle = TaskHandle(task_id="task-xyz", result="ok", _agent_url="http://test:8787")

        with patch("a2a_lite.orchestration.cancel_remote_task", new_callable=AsyncMock) as mock:
            mock.return_value = {"id": "task-xyz", "status": {"state": "canceled"}}
            result = await handle.cancel()
            assert isinstance(result, dict)
            assert result["status"]["state"] == "canceled"
            mock.assert_called_once_with("http://test:8787", "task-xyz", 10.0)


class TestAgentNetworkTaskLifecycle:
    @pytest.mark.asyncio
    async def test_get_task(self):
        net = AgentNetwork()
        net.add("test", "http://test:8787")

        response_data = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {"id": "task-xyz", "status": {"state": "completed"}},
        }

        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await net.get_task("test", "task-xyz")
            assert result["id"] == "task-xyz"
            assert result["status"]["state"] == "completed"

    @pytest.mark.asyncio
    async def test_cancel_task(self):
        net = AgentNetwork()
        net.add("test", "http://test:8787")

        response_data = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {"id": "task-xyz", "status": {"state": "canceled"}},
        }

        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await net.cancel_task("test", "task-xyz")
            assert result["id"] == "task-xyz"
            assert result["status"]["state"] == "canceled"

    @pytest.mark.asyncio
    async def test_get_task_unknown_agent(self):
        net = AgentNetwork()
        with pytest.raises(KeyError, match="not found"):
            await net.get_task("missing", "task-xyz")

    @pytest.mark.asyncio
    async def test_cancel_task_unknown_agent(self):
        net = AgentNetwork()
        with pytest.raises(KeyError, match="not found"):
            await net.cancel_task("missing", "task-xyz")


class TestAgentNetworkCallWithHandle:
    @pytest.mark.asyncio
    async def test_call_return_handle_true(self):
        net = AgentNetwork()
        net.add("test", "http://test:8787")

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.return_value = ("hello", "task-handle-123")
            handle = await net.call("test", "greet", return_handle=True, city="NYC")
            assert isinstance(handle, TaskHandle)
            assert handle.task_id == "task-handle-123"
            assert handle.result == "hello"
            assert handle._agent_url == "http://test:8787"

    @pytest.mark.asyncio
    async def test_call_return_handle_false(self):
        net = AgentNetwork()
        net.add("test", "http://test:8787")

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.return_value = ("hello", "task-handle-123")
            result = await net.call("test", "greet", city="NYC")
            assert result == "hello"
            assert not isinstance(result, TaskHandle)


class TestAgentCardInfo:
    def test_fields(self):
        card = AgentCardInfo(
            name="TestAgent",
            description="A test agent",
            url="http://test:8787",
            version="1.0.0",
            skills=[{"id": "greet", "name": "greet"}],
            supports_streaming=True,
            supports_push=False,
            raw={"name": "TestAgent"},
        )
        assert card.name == "TestAgent"
        assert card.description == "A test agent"
        assert card.url == "http://test:8787"
        assert card.version == "1.0.0"
        assert len(card.skills) == 1
        assert card.supports_streaming is True
        assert card.supports_push is False
        assert card.raw == {"name": "TestAgent"}


class TestDiscover:
    @pytest.mark.asyncio
    async def test_discover_fetches_card(self):
        card_data = {
            "name": "RemoteAgent",
            "description": "A remote agent",
            "url": "http://remote:8787",
            "version": "2.0.0",
            "capabilities": {"streaming": True, "pushNotifications": False},
            "skills": [{"id": "forecast", "name": "forecast", "description": "Weather forecast"}],
        }

        mock_response = MagicMock()
        mock_response.json.return_value = card_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            card = await discover("http://remote:8787")
            assert isinstance(card, AgentCardInfo)
            assert card.name == "RemoteAgent"
            assert card.version == "2.0.0"
            assert card.supports_streaming is True
            assert card.supports_push is False
            assert len(card.skills) == 1
            assert card.raw == card_data
            mock_client.get.assert_called_once_with("http://remote:8787/.well-known/agent.json")


class TestGetRemoteTask:
    @pytest.mark.asyncio
    async def test_get_remote_task(self):
        response_data = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {"id": "task-xyz", "status": {"state": "completed"}},
        }

        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await get_remote_task("http://agent:8787", "task-xyz")
            assert result["id"] == "task-xyz"
            assert result["status"]["state"] == "completed"

    @pytest.mark.asyncio
    async def test_get_remote_task_error(self):
        from a2a_lite.errors import RemoteAgentError

        response_data = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "error": {"code": -32000, "message": "Task not found"},
        }

        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(RemoteAgentError):
                await get_remote_task("http://agent:8787", "task-xyz")


class TestCancelRemoteTask:
    @pytest.mark.asyncio
    async def test_cancel_remote_task(self):
        response_data = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {"id": "task-xyz", "status": {"state": "canceled"}},
        }

        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await cancel_remote_task("http://agent:8787", "task-xyz")
            assert result["id"] == "task-xyz"
            assert result["status"]["state"] == "canceled"

    @pytest.mark.asyncio
    async def test_cancel_remote_task_error(self):
        from a2a_lite.errors import RemoteAgentError

        response_data = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "error": {"code": -32000, "message": "Cannot cancel"},
        }

        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(RemoteAgentError):
                await cancel_remote_task("http://agent:8787", "task-xyz")


class TestAgentNetworkDiscover:
    @pytest.mark.asyncio
    async def test_discover_caches_card(self):
        net = AgentNetwork()
        net.add("test", "http://test:8787")

        card = AgentCardInfo(
            name="TestAgent",
            description="Test",
            url="http://test:8787",
            version="1.0.0",
            skills=[],
            supports_streaming=False,
            supports_push=False,
            raw={},
        )

        with patch("a2a_lite.orchestration.discover", new_callable=AsyncMock, return_value=card):
            result = await net.discover("test")
            assert result is card
            assert net.get_card("test") is card

    @pytest.mark.asyncio
    async def test_discover_unknown_agent(self):
        net = AgentNetwork()
        with pytest.raises(KeyError, match="not found"):
            await net.discover("missing")

    def test_get_card_none(self):
        net = AgentNetwork()
        assert net.get_card("missing") is None


def _make_sse_lines(events: list[dict]) -> list[str]:
    """Build raw SSE lines from a list of event dicts."""
    lines = []
    for event in events:
        lines.append(f"data: {json.dumps(event)}")
        lines.append("")  # blank line between events
    return lines


class _FakeAsyncLineIterator:
    """Async iterator over a list of strings, simulating response.aiter_lines()."""

    def __init__(self, lines: list[str]):
        self._lines = lines
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._lines):
            raise StopAsyncIteration
        line = self._lines[self._index]
        self._index += 1
        return line


def _build_streaming_mocks(sse_lines: list[str]):
    """Build mock httpx client + response for SSE streaming tests.

    Returns (mock_client_cls,) ready to patch httpx.AsyncClient.
    httpx.AsyncClient.stream() returns an async context manager (not a coroutine),
    so we use a custom class to match that protocol.
    """
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.aiter_lines.return_value = _FakeAsyncLineIterator(sse_lines)

    class _StreamCM:
        async def __aenter__(self):
            return mock_response

        async def __aexit__(self, *args):
            return False

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=_StreamCM())

    class _ClientCM:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return mock_client

        async def __aexit__(self, *args):
            return False

    return _ClientCM, mock_client


class TestStreamRemoteSkill:
    @pytest.mark.asyncio
    async def test_yields_artifact_chunks_in_order(self):
        """Artifact text parts are yielded in order, stops at final=True."""
        sse_events = [
            {"id": "task-1", "artifact": {"parts": [{"kind": "text", "text": "Hello "}]}, "final": False},
            {"id": "task-1", "artifact": {"parts": [{"kind": "text", "text": "world"}]}, "final": False},
            {"id": "task-1", "status": {"state": "completed"}, "final": True},
        ]
        client_cls, _ = _build_streaming_mocks(_make_sse_lines(sse_events))

        with patch("httpx.AsyncClient", client_cls):
            chunks = []
            async for chunk in stream_remote_skill("http://test:8787", "skill", {"x": 1}):
                chunks.append(chunk)

        assert chunks == ["Hello ", "world"]

    @pytest.mark.asyncio
    async def test_yields_from_result_artifact_pattern(self):
        """Handles the result.artifact nested pattern."""
        sse_events = [
            {"result": {"artifact": {"parts": [{"type": "text", "text": "chunk1"}]}}},
            {"id": "task-1", "status": {"state": "completed"}, "final": True},
        ]
        client_cls, _ = _build_streaming_mocks(_make_sse_lines(sse_events))

        with patch("httpx.AsyncClient", client_cls):
            chunks = []
            async for chunk in stream_remote_skill("http://test:8787", "skill", {}):
                chunks.append(chunk)

        assert chunks == ["chunk1"]

    @pytest.mark.asyncio
    async def test_stops_at_final_true(self):
        """Generator stops when final=True, ignoring subsequent events."""
        sse_events = [
            {"id": "task-1", "artifact": {"parts": [{"kind": "text", "text": "A"}]}, "final": False},
            {"id": "task-1", "status": {"state": "completed"}, "final": True},
            # This should never be reached
            {"id": "task-1", "artifact": {"parts": [{"kind": "text", "text": "B"}]}, "final": False},
        ]
        client_cls, _ = _build_streaming_mocks(_make_sse_lines(sse_events))

        with patch("httpx.AsyncClient", client_cls):
            chunks = []
            async for chunk in stream_remote_skill("http://test:8787", "skill", {}):
                chunks.append(chunk)

        assert chunks == ["A"]

    @pytest.mark.asyncio
    async def test_raises_on_failed_state(self):
        """RemoteAgentError raised when status.state is 'failed'."""
        from a2a_lite.errors import RemoteAgentError

        sse_events = [
            {"id": "task-1", "artifact": {"parts": [{"kind": "text", "text": "partial"}]}, "final": False},
            {
                "id": "task-1",
                "status": {
                    "state": "failed",
                    "message": {"parts": [{"kind": "text", "text": "Something went wrong"}]},
                },
                "final": True,
            },
        ]
        client_cls, _ = _build_streaming_mocks(_make_sse_lines(sse_events))

        with patch("httpx.AsyncClient", client_cls):
            chunks = []
            with pytest.raises(RemoteAgentError, match="Something went wrong"):
                async for chunk in stream_remote_skill("http://test:8787", "skill", {}):
                    chunks.append(chunk)

        # The first chunk should have been yielded before the error
        assert chunks == ["partial"]

    @pytest.mark.asyncio
    async def test_skips_comment_and_event_lines(self):
        """Comment lines and event: lines are silently skipped."""
        raw_lines = [
            ": this is a comment",
            "event: message",
            f'data: {json.dumps({"id": "t1", "artifact": {"parts": [{"kind": "text", "text": "ok"}]}, "final": False})}',
            "",
            f'data: {json.dumps({"id": "t1", "status": {"state": "completed"}, "final": True})}',
            "",
        ]
        client_cls, _ = _build_streaming_mocks(raw_lines)

        with patch("httpx.AsyncClient", client_cls):
            chunks = []
            async for chunk in stream_remote_skill("http://test:8787", "skill", {}):
                chunks.append(chunk)

        assert chunks == ["ok"]

    @pytest.mark.asyncio
    async def test_uses_message_stream_method(self):
        """Verify the request body uses method 'message/stream'."""
        sse_events = [
            {"id": "task-1", "status": {"state": "completed"}, "final": True},
        ]
        client_cls, mock_client = _build_streaming_mocks(_make_sse_lines(sse_events))

        with patch("httpx.AsyncClient", client_cls):
            async for _ in stream_remote_skill("http://test:8787", "skill", {"a": 1}):
                pass

        # Check the stream() call args
        call_args = mock_client.stream.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == "http://test:8787"
        body = call_args[1]["json"] if "json" in call_args[1] else call_args[0][2]
        assert body["method"] == "message/stream"


class TestAgentNetworkStream:
    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self):
        net = AgentNetwork()
        net.add("test", "http://test:8787")

        sse_events = [
            {"id": "task-1", "artifact": {"parts": [{"kind": "text", "text": "chunk1"}]}, "final": False},
            {"id": "task-1", "artifact": {"parts": [{"kind": "text", "text": "chunk2"}]}, "final": False},
            {"id": "task-1", "status": {"state": "completed"}, "final": True},
        ]
        client_cls, _ = _build_streaming_mocks(_make_sse_lines(sse_events))

        with patch("httpx.AsyncClient", client_cls):
            chunks = []
            async for chunk in net.stream("test", "skill", x=1):
                chunks.append(chunk)

        assert chunks == ["chunk1", "chunk2"]

    @pytest.mark.asyncio
    async def test_stream_unknown_agent(self):
        net = AgentNetwork()
        with pytest.raises(KeyError, match="not found"):
            async for _ in net.stream("missing", "skill"):
                pass


class TestAgentDelegateStream:
    @pytest.mark.asyncio
    async def test_delegate_stream_returns_generator(self):
        net = AgentNetwork()
        net.add("test", "http://test:8787")
        agent = Agent(name="Test", description="Test", network=net)

        sse_events = [
            {"id": "task-1", "artifact": {"parts": [{"kind": "text", "text": "a"}]}, "final": False},
            {"id": "task-1", "artifact": {"parts": [{"kind": "text", "text": "b"}]}, "final": False},
            {"id": "task-1", "status": {"state": "completed"}, "final": True},
        ]
        client_cls, _ = _build_streaming_mocks(_make_sse_lines(sse_events))

        with patch("httpx.AsyncClient", client_cls):
            gen = await agent.delegate("test", "skill", stream=True, x=1)
            chunks = []
            async for chunk in gen:
                chunks.append(chunk)

        assert chunks == ["a", "b"]

    @pytest.mark.asyncio
    async def test_delegate_stream_false_unchanged(self):
        """stream=False (default) still uses the blocking path."""
        agent = Agent(name="Test", description="Test")

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.return_value = ("result", "task-123")
            result = await agent.delegate("http://other:8787", "skill", x=1)
            assert result == "result"
