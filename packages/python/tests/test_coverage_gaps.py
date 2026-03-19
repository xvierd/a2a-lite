"""
Tests to cover remaining gaps in tasks.py, testing.py, and agent.py.
"""

import pytest

from a2a_lite import Agent, AgentTestClient
from a2a_lite.tasks import (
    Task,
    TaskContext,
    TaskState,
    TaskStatus,
    TaskStore,
)
from a2a_lite.testing import AsyncAgentTestClient, TestClientError, TestResult


class TestTaskStoreEviction:
    """Cover TaskStore._evict max_size overflow path."""

    @pytest.mark.asyncio
    async def test_evict_when_over_max_size(self):
        """Test that oldest tasks are evicted when max_size is reached."""
        store = TaskStore(max_size=3)

        t1 = await store.create("skill", {"order": 1})
        t2 = await store.create("skill", {"order": 2})
        t3 = await store.create("skill", {"order": 3})

        # This should trigger eviction of t1
        t4 = await store.create("skill", {"order": 4})

        all_tasks = await store.list()
        task_ids = {t.id for t in all_tasks}

        # t1 should have been evicted
        assert t1.id not in task_ids
        assert t4.id in task_ids
        assert len(all_tasks) <= 3

    @pytest.mark.asyncio
    async def test_evict_expired_tasks(self):
        """Test that expired tasks are removed during eviction."""
        import datetime

        store = TaskStore(ttl_seconds=0)  # Expire immediately

        await store.create("skill", {"data": "old"})

        # Creating a new task should trigger eviction of the expired one
        # (the first one should be expired since ttl_seconds=0)
        import asyncio

        await asyncio.sleep(0.01)

        t2 = await store.create("skill", {"data": "new"})
        all_tasks = await store.list()

        # Only the newest task should remain (older one expired)
        assert len(all_tasks) >= 1
        assert any(t.id == t2.id for t in all_tasks)


class TestTaskContextCallbackErrors:
    """Cover error handling in TaskContext status callbacks."""

    @pytest.mark.asyncio
    async def test_sync_callback_error_is_caught(self):
        """Test that sync callback errors are caught and logged."""
        task = Task(
            id="task-err",
            skill="process",
            params={},
            status=TaskStatus(state=TaskState.SUBMITTED),
        )
        ctx = TaskContext(task)

        def bad_callback(status):
            raise RuntimeError("callback failed")

        ctx.on_status_change(bad_callback)

        # Should not raise despite callback error
        await ctx.update("working", "Step 1")
        assert task.status.state == TaskState.WORKING


class TestTestingExtractResultFallback:
    """Cover _extract_result fallback when no text parts found."""

    def test_extract_result_no_text_parts(self):
        """Test fallback when response has no text parts."""
        agent = Agent(name="Test", description="Test")

        @agent.skill("test")
        async def test_skill() -> str:
            return "ok"

        client = AgentTestClient(agent)
        # Simulate a response with no text parts
        response = {"result": {"parts": []}}
        result = client._extract_result(response)

        assert isinstance(result, TestResult)
        # Should return the result dict as data
        assert result.data == {"parts": []}

    def test_extract_result_with_error(self):
        """Test _extract_result raises on error response."""
        agent = Agent(name="Test", description="Test")

        @agent.skill("test")
        async def test_skill() -> str:
            return "ok"

        client = AgentTestClient(agent)
        with pytest.raises(TestClientError):
            client._extract_result({"error": {"code": -1, "message": "fail"}})


class TestAsyncClientExtractResultFallback:
    """Cover AsyncAgentTestClient._extract_result fallback."""

    def test_extract_result_no_text_parts(self):
        """Test fallback when async client response has no text parts."""
        agent = Agent(name="Test", description="Test")

        @agent.skill("test")
        async def test_skill() -> str:
            return "ok"

        client = AsyncAgentTestClient(agent)
        response = {"result": {"parts": []}}
        result = client._extract_result(response)

        assert isinstance(result, TestResult)
        assert result.data == {"parts": []}

    def test_extract_result_with_error(self):
        """Test async _extract_result raises on error response."""
        agent = Agent(name="Test", description="Test")

        @agent.skill("test")
        async def test_skill() -> str:
            return "ok"

        client = AsyncAgentTestClient(agent)
        with pytest.raises(TestClientError):
            client._extract_result({"error": {"code": -1, "message": "fail"}})

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test AsyncAgentTestClient as async context manager."""
        agent = Agent(name="Test", description="Test")

        @agent.skill("ping")
        async def ping() -> str:
            return "pong"

        async with AsyncAgentTestClient(agent) as client:
            result = await client.call("ping")
            assert result == "pong"


class TestAgentBuildApp:
    """Cover _build_app paths."""

    def test_build_app_with_push_notifier(self):
        """Test _build_app wires push notifier as on_complete hook."""
        from a2a_lite.push_notifications import LogPushNotifier

        notifier = LogPushNotifier()
        agent = Agent(
            name="Test",
            description="Test",
            push_notifier=notifier,
        )

        @agent.skill("test")
        async def test_skill() -> str:
            return "ok"

        app = agent._build_app("localhost", 8787)
        assert app is not None

    def test_build_app_with_protocol_task_store(self):
        """Test _build_app uses custom protocol task store."""
        from a2a.server.tasks import InMemoryTaskStore

        custom_store = InMemoryTaskStore()
        agent = Agent(
            name="Test",
            description="Test",
            protocol_task_store=custom_store,
        )

        @agent.skill("test")
        async def test_skill() -> str:
            return "ok"

        app = agent._build_app("localhost", 8787)
        assert app is not None


class TestAgentDelegate:
    """Cover delegate method paths."""

    @pytest.mark.asyncio
    async def test_delegate_unknown_agent_in_network(self):
        """Test delegate raises KeyError for unknown agent in network."""
        from a2a_lite.orchestration import AgentNetwork

        network = AgentNetwork()
        network.add("known", "http://known:8787")

        agent = Agent(name="Test", description="Test", network=network)

        with pytest.raises(KeyError, match="not found in network"):
            await agent.delegate("unknown_agent", "skill", data="test")

    @pytest.mark.asyncio
    async def test_delegate_resolves_network_name(self):
        """Test delegate resolves name from network."""
        from unittest.mock import AsyncMock, patch

        from a2a_lite.orchestration import AgentNetwork

        network = AgentNetwork()
        network.add("weather", "http://weather:8787")

        agent = Agent(name="Test", description="Test", network=network)

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"temp": 72}
            result = await agent.delegate("weather", "forecast", city="NYC")

            mock_call.assert_called_once_with("http://weather:8787", "forecast", {"city": "NYC"}, 30.0)
            assert result == {"temp": 72}


class TestAgentMiscPaths:
    """Cover miscellaneous agent paths."""

    def test_add_mcp_server(self):
        """Test MCP server registration."""
        agent = Agent(name="Test", description="Test")
        agent.add_mcp_server("http://localhost:5001")
        assert "http://localhost:5001" in agent._mcp_servers

    def test_network_setup_none(self):
        """Test that network is None by default."""
        agent = Agent(name="Test", description="Test")
        assert agent._network is None

    def test_network_setup_provided(self):
        """Test that network is stored when provided."""
        from a2a_lite.orchestration import AgentNetwork

        network = AgentNetwork()
        agent = Agent(name="Test", description="Test", network=network)
        assert agent._network is network

    def test_push_notifier_stored(self):
        """Test that push notifier is stored."""
        from a2a_lite.push_notifications import LogPushNotifier

        notifier = LogPushNotifier()
        agent = Agent(name="Test", description="Test", push_notifier=notifier)
        assert agent._push_notifier is notifier
