"""
Tests for the orchestration module (AgentNetwork, delegate).
"""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from a2a_lite.orchestration import AgentNetwork, _call_remote_skill, _extract_result
from a2a_lite import Agent


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
            mock.return_value = "hello"
            result = await net.call("test", "greet", city="NYC")
            assert result == "hello"
            mock.assert_called_once_with(
                "http://test:8787", "greet", {"city": "NYC"}, 30.0
            )

    @pytest.mark.asyncio
    async def test_broadcast(self):
        net = AgentNetwork()
        net.add("a", "http://a:8787")
        net.add("b", "http://b:8787")

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.side_effect = ["result_a", "result_b"]
            results = await net.broadcast("skill", x=1)
            assert "a" in results
            assert "b" in results

    @pytest.mark.asyncio
    async def test_broadcast_handles_errors(self):
        net = AgentNetwork()
        net.add("a", "http://a:8787")
        net.add("b", "http://b:8787")

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.side_effect = ["ok", Exception("fail")]
            results = await net.broadcast("skill")
            assert results["a"] == "ok"
            assert "error" in results["b"]


class TestExtractResult:
    def test_extract_text_part(self):
        response = {
            "result": {
                "parts": [{"kind": "text", "text": '"hello"'}]
            }
        }
        assert _extract_result(response) == "hello"

    def test_extract_json_part(self):
        response = {
            "result": {
                "parts": [{"kind": "text", "text": '{"key": "value"}'}]
            }
        }
        assert _extract_result(response) == {"key": "value"}

    def test_extract_plain_text(self):
        response = {
            "result": {
                "parts": [{"kind": "text", "text": "just text"}]
            }
        }
        assert _extract_result(response) == "just text"

    def test_extract_error(self):
        response = {"error": {"code": -32000, "message": "fail"}}
        result = _extract_result(response)
        assert result["code"] == -32000

    def test_extract_empty_result(self):
        response = {"result": {}}
        assert _extract_result(response) == {}

    def test_extract_type_text(self):
        response = {
            "result": {
                "parts": [{"type": "text", "text": "hello"}]
            }
        }
        assert _extract_result(response) == "hello"


class TestAgentDelegate:
    @pytest.mark.asyncio
    async def test_delegate_with_url(self):
        agent = Agent(name="Test", description="Test")

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.return_value = "result"
            result = await agent.delegate("http://other:8787", "skill", x=1)
            assert result == "result"

    @pytest.mark.asyncio
    async def test_delegate_with_network_name(self):
        net = AgentNetwork()
        net.add("other", "http://other:8787")
        agent = Agent(name="Test", description="Test", network=net)

        with patch("a2a_lite.orchestration._call_remote_skill", new_callable=AsyncMock) as mock:
            mock.return_value = "result"
            result = await agent.delegate("other", "skill", x=1)
            assert result == "result"
            mock.assert_called_once_with("http://other:8787", "skill", {"x": 1}, 30.0)

    @pytest.mark.asyncio
    async def test_delegate_unknown_name(self):
        net = AgentNetwork()
        agent = Agent(name="Test", description="Test", network=net)

        with pytest.raises(KeyError, match="not found"):
            await agent.delegate("missing", "skill")
