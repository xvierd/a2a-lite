"""
Tests for the orchestration module (AgentNetwork, delegate).
"""

import json
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import httpx
import pytest

from a2a_lite import Agent
from a2a_lite.orchestration import (
    AgentCardInfo,
    AgentNetwork,
    TaskHandle,
    _call_remote_skill,
    cancel_remote_task,
    discover,
    get_remote_task,
    stream_remote_skill,
)


def task_result(text, task_id):
    return {"task": {"id": task_id, "contextId": "context", "artifacts": [{"parts": [{"text": text}]}]}}


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
            mock.return_value = task_result("hello", "task-123")
            result = await net.call("test", "greet", city="NYC")
            assert result == "hello"
            mock.assert_called_once_with("http://test:8787", "greet", {"city": "NYC"}, 30.0, client_config=ANY)

    @pytest.mark.asyncio
    async def test_call_with_param_named_name_and_skill(self):
        """A remote skill parameter named 'name' or 'skill' must not collide
        with the routing arguments of AgentNetwork.call."""
        net = AgentNetwork()
        net.add("test", "http://test:8787")

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.return_value = task_result("hello Bob", "task-123")
            result = await net.call("test", "greet", name="Bob", skill="advanced")
            assert result == "hello Bob"
            mock.assert_called_once_with(
                "http://test:8787", "greet", {"name": "Bob", "skill": "advanced"}, 30.0, client_config=ANY
            )

    @pytest.mark.asyncio
    async def test_broadcast_with_param_named_skill(self):
        net = AgentNetwork()
        net.add("a", "http://a:8787")

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.return_value = task_result("ok", "tid-a")
            results = await net.broadcast("greet", skill="advanced")
            assert results["a"] == "ok"
            mock.assert_called_once_with("http://a:8787", "greet", {"skill": "advanced"}, 30.0, client_config=ANY)

    @pytest.mark.asyncio
    async def test_broadcast(self):
        net = AgentNetwork()
        net.add("a", "http://a:8787")
        net.add("b", "http://b:8787")

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.side_effect = [task_result("result_a", "tid-a"), task_result("result_b", "tid-b")]
            results = await net.broadcast("skill", x=1)
            assert results["a"] == "result_a"
            assert results["b"] == "result_b"

    @pytest.mark.asyncio
    async def test_broadcast_handles_errors(self):
        net = AgentNetwork()
        net.add("a", "http://a:8787")
        net.add("b", "http://b:8787")

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.side_effect = [task_result("ok", "tid-a"), Exception("fail")]
            results = await net.broadcast("skill")
            assert results["a"] == "ok"
            assert "error" in results["b"]


class TestExtractResult:
    @pytest.mark.parametrize(
        ("result", "expected"),
        [
            ({"parts": [{"kind": "text", "text": '"hello"'}]}, "hello"),
            ({"parts": [{"kind": "text", "text": '{"key": "value"}'}]}, {"key": "value"}),
            ({"parts": [{"kind": "text", "text": "just text"}]}, "just text"),
            ({"parts": [{"type": "text", "text": "hello"}]}, "hello"),
            ({}, {}),
        ],
    )
    async def test_parses_legacy_results(self, rpc_reply, result, expected):
        rpc_reply(result=result)
        network = AgentNetwork({"test": "http://test"})
        assert await network.call("test", "skill") == expected


class TestAgentDelegate:
    @pytest.mark.asyncio
    async def test_delegate_with_url(self):
        agent = Agent(name="Test", description="Test")

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.return_value = task_result("result", "task-123")
            result = await agent.delegate("http://other:8787", "skill", x=1)
            assert result == "result"

    @pytest.mark.asyncio
    async def test_delegate_with_network_name(self):
        net = AgentNetwork()
        net.add("other", "http://other:8787")
        agent = Agent(name="Test", description="Test", network=net)

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.return_value = task_result("result", "task-456")
            result = await agent.delegate("other", "skill", x=1)
            assert result == "result"
            mock.assert_called_once_with("http://other:8787", "skill", {"x": 1}, 30.0, client_config=ANY)

    @pytest.mark.asyncio
    async def test_delegate_with_param_named_target_and_skill(self):
        """Skill params named 'target' or 'skill' must not collide with the
        routing arguments of Agent.delegate."""
        agent = Agent(name="Test", description="Test")

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.return_value = task_result("result", "task-123")
            result = await agent.delegate("http://other:8787", "greet", target="Bob", skill="advanced")
            assert result == "result"
            mock.assert_called_once_with(
                "http://other:8787", "greet", {"target": "Bob", "skill": "advanced"}, 30.0, client_config=ANY
            )

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
            mock.return_value = task_result("result", "task-789")
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
            mock_call.return_value = task_result("result", "task-abc")
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
    def test_message_only_response_cannot_create_handle(self):
        with pytest.raises(ValueError, match="without a task ID"):
            TaskHandle(task_id="", result="message", _agent_url="http://test")

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
            mock.assert_called_once_with("http://test:8787", "task-xyz", 10.0, client_config=ANY)

    @pytest.mark.asyncio
    async def test_cancel(self):
        handle = TaskHandle(task_id="task-xyz", result="ok", _agent_url="http://test:8787")

        with patch("a2a_lite.orchestration.cancel_remote_task", new_callable=AsyncMock) as mock:
            mock.return_value = {"id": "task-xyz", "status": {"state": "canceled"}}
            result = await handle.cancel()
            assert isinstance(result, dict)
            assert result["status"]["state"] == "canceled"
            mock.assert_called_once_with("http://test:8787", "task-xyz", 10.0, client_config=ANY)


class TestAgentNetworkTaskLifecycle:
    @pytest.mark.asyncio
    async def test_get_task(self, rpc_reply):
        net = AgentNetwork()
        net.add("test", "http://test:8787")

        rpc_reply(result={"id": "task-xyz", "status": {"state": "completed"}})
        result = await net.get_task("test", "task-xyz")
        assert result["id"] == "task-xyz"
        assert result["status"]["state"] == "completed"

    @pytest.mark.asyncio
    async def test_cancel_task(self, rpc_reply):
        net = AgentNetwork()
        net.add("test", "http://test:8787")

        rpc_reply(result={"id": "task-xyz", "status": {"state": "canceled"}})
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
            mock.return_value = task_result("hello", "task-handle-123")
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
            mock.return_value = task_result("hello", "task-handle-123")
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
    async def test_selects_jsonrpc_instead_of_first_interface(self, mock_http):
        card = {
            "supportedInterfaces": [
                {"url": "localhost:50051", "protocolBinding": "GRPC", "protocolVersion": "1.0"},
                {"url": "https://agent.example/rest", "protocolBinding": "HTTP+JSON", "protocolVersion": "1.0"},
                {"url": "https://agent.example/rpc", "protocolBinding": "JSONRPC", "protocolVersion": "1.0.1"},
            ]
        }
        mock_http(lambda request: httpx.Response(200, json=card))
        assert (await discover("https://agent.example")).url == "https://agent.example/rpc"

    @pytest.mark.parametrize(
        "binding,version", [("GRPC", "1.0"), ("HTTP+JSON", "1.0"), ("JSONRPC", "0.3"), ("JSONRPC", "2.0")]
    )
    async def test_rejects_unsupported_interface(self, mock_http, binding, version):
        from a2a_lite.errors import RemoteAgentError

        card = {
            "supportedInterfaces": [
                {"url": "https://agent.example", "protocolBinding": binding, "protocolVersion": version}
            ]
        }
        mock_http(lambda request: httpx.Response(200, json=card))
        with pytest.raises(RemoteAgentError, match="no supported"):
            await discover("https://agent.example")

    @pytest.mark.asyncio
    async def test_discover_fetches_card(self):
        card_data = {
            "name": "RemoteAgent",
            "description": "A remote agent",
            "supportedInterfaces": [
                {"url": "http://remote:8787", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
            ],
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
            mock_client.get.assert_called_once_with(
                "http://remote:8787/.well-known/agent-card.json", headers={"A2A-Version": "1.0"}
            )


class TestGetRemoteTask:
    @pytest.mark.asyncio
    async def test_get_remote_task(self, rpc_reply):
        rpc_reply(result={"id": "task-xyz", "status": {"state": "completed"}})
        result = await get_remote_task("http://agent:8787", "task-xyz")
        assert result["id"] == "task-xyz"
        assert result["status"]["state"] == "completed"

    @pytest.mark.asyncio
    async def test_get_remote_task_error(self, rpc_reply):
        from a2a_lite.errors import RemoteAgentError

        rpc_reply(error={"code": -32000, "message": "Task not found"})
        with pytest.raises(RemoteAgentError):
            await get_remote_task("http://agent:8787", "task-xyz")


class TestCancelRemoteTask:
    @pytest.mark.asyncio
    async def test_cancel_remote_task(self, rpc_reply):
        rpc_reply(result={"id": "task-xyz", "status": {"state": "canceled"}})
        result = await cancel_remote_task("http://agent:8787", "task-xyz")
        assert result["id"] == "task-xyz"
        assert result["status"]["state"] == "canceled"

    @pytest.mark.asyncio
    async def test_cancel_remote_task_error(self, rpc_reply):
        from a2a_lite.errors import RemoteAgentError

        rpc_reply(error={"code": -32000, "message": "Cannot cancel"})
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


class TestStreamRemoteSkill:
    @pytest.mark.asyncio
    async def test_yields_artifact_chunks_in_order(self, sse_reply):
        """Artifact text parts are yielded in order, stops at terminal state."""
        sse_events = [
            {"result": {"artifactUpdate": {"artifact": {"parts": [{"text": "Hello "}]}}}},
            {"result": {"artifactUpdate": {"artifact": {"parts": [{"text": "world"}]}}}},
            {"result": {"statusUpdate": {"status": {"state": "TASK_STATE_COMPLETED"}}}},
        ]
        sse_reply(sse_events)
        chunks = []
        async for chunk in stream_remote_skill("http://test:8787", "skill", {"x": 1}):
            chunks.append(chunk)

        assert chunks == ["Hello ", "world"]

    @pytest.mark.asyncio
    async def test_yields_from_result_artifact_pattern(self, sse_reply):
        """Handles the result.artifactUpdate nested pattern."""
        sse_events = [
            {"result": {"artifactUpdate": {"artifact": {"parts": [{"text": "chunk1"}]}}}},
            {"result": {"statusUpdate": {"status": {"state": "TASK_STATE_COMPLETED"}}}},
        ]
        sse_reply(sse_events)
        chunks = []
        async for chunk in stream_remote_skill("http://test:8787", "skill", {}):
            chunks.append(chunk)

        assert chunks == ["chunk1"]

    @pytest.mark.asyncio
    async def test_stops_at_terminal_state(self, sse_reply):
        """Generator stops at a terminal state, ignoring subsequent events."""
        sse_events = [
            {"result": {"artifactUpdate": {"artifact": {"parts": [{"text": "A"}]}}}},
            {"result": {"statusUpdate": {"status": {"state": "TASK_STATE_COMPLETED"}}}},
            # This should never be reached
            {"result": {"artifactUpdate": {"artifact": {"parts": [{"text": "B"}]}}}},
        ]
        sse_reply(sse_events)
        chunks = []
        async for chunk in stream_remote_skill("http://test:8787", "skill", {}):
            chunks.append(chunk)

        assert chunks == ["A"]

    @pytest.mark.asyncio
    async def test_raises_on_failed_state(self, sse_reply):
        """RemoteAgentError raised when status.state is TASK_STATE_FAILED."""
        from a2a_lite.errors import RemoteAgentError

        sse_events = [
            {"result": {"artifactUpdate": {"artifact": {"parts": [{"text": "partial"}]}}}},
            {
                "result": {
                    "statusUpdate": {
                        "status": {
                            "state": "TASK_STATE_FAILED",
                            "message": {"parts": [{"text": "Something went wrong"}]},
                        }
                    }
                }
            },
        ]
        sse_reply(sse_events)
        chunks = []
        with pytest.raises(RemoteAgentError, match="Something went wrong"):
            async for chunk in stream_remote_skill("http://test:8787", "skill", {}):
                chunks.append(chunk)

        # The first chunk should have been yielded before the error
        assert chunks == ["partial"]

    @pytest.mark.asyncio
    async def test_skips_comment_and_event_lines(self, sse_reply):
        """Comment lines and event: lines are silently skipped."""
        sse_events = [
            {"result": {"artifactUpdate": {"artifact": {"parts": [{"text": "ok"}]}}}},
            {"result": {"statusUpdate": {"status": {"state": "TASK_STATE_COMPLETED"}}}},
        ]
        sse_reply(sse_events, prefix=": this is a comment\nevent: message\n")
        chunks = [chunk async for chunk in stream_remote_skill("http://test:8787", "skill", {})]
        assert chunks == ["ok"]

    @pytest.mark.asyncio
    async def test_uses_message_stream_method(self, sse_reply):
        """Verify the request body uses method 'SendStreamingMessage'."""
        sse_events = [
            {"result": {"statusUpdate": {"status": {"state": "TASK_STATE_COMPLETED"}}}},
        ]
        requests = sse_reply(sse_events)
        async for _ in stream_remote_skill("http://test:8787", "skill", {"a": 1}):
            pass
        (request,) = requests
        assert request.method == "POST"
        assert str(request.url) == "http://test:8787"
        body = json.loads(request.content)
        assert body["method"] == "SendStreamingMessage"


class TestAgentNetworkStream:
    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self, sse_reply):
        net = AgentNetwork()
        net.add("test", "http://test:8787")

        sse_events = [
            {"result": {"artifactUpdate": {"artifact": {"parts": [{"text": "chunk1"}]}}}},
            {"result": {"artifactUpdate": {"artifact": {"parts": [{"text": "chunk2"}]}}}},
            {"result": {"statusUpdate": {"status": {"state": "TASK_STATE_COMPLETED"}}}},
        ]
        sse_reply(sse_events)
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
    async def test_delegate_stream_returns_generator(self, sse_reply):
        net = AgentNetwork()
        net.add("test", "http://test:8787")
        agent = Agent(name="Test", description="Test", network=net)

        sse_events = [
            {"result": {"artifactUpdate": {"artifact": {"parts": [{"text": "a"}]}}}},
            {"result": {"artifactUpdate": {"artifact": {"parts": [{"text": "b"}]}}}},
            {"result": {"statusUpdate": {"status": {"state": "TASK_STATE_COMPLETED"}}}},
        ]
        sse_reply(sse_events)
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
            mock.return_value = task_result("result", "task-123")
            result = await agent.delegate("http://other:8787", "skill", x=1)
            assert result == "result"
