"""
Tests for the MCP integration module.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from a2a_lite.mcp import MCPClient, _extract_mcp_content
from a2a_lite import Agent


class TestMCPClient:
    def test_create_empty(self):
        client = MCPClient()
        assert client._server_urls == []

    def test_create_with_urls(self):
        client = MCPClient(server_urls=["http://localhost:5001"])
        assert len(client._server_urls) == 1

    def test_add_server(self):
        client = MCPClient()
        client.add_server("http://localhost:5001")
        assert "http://localhost:5001" in client._server_urls

    def test_repr(self):
        client = MCPClient(server_urls=["http://localhost:5001"])
        assert "localhost:5001" in repr(client)

    @pytest.mark.asyncio
    async def test_call_tool_no_servers(self):
        client = MCPClient()
        with pytest.raises(ValueError, match="not found"):
            await client.call_tool("web_search", query="test")

    @pytest.mark.asyncio
    async def test_list_tools_no_servers(self):
        client = MCPClient()
        result = await client.list_tools()
        assert result == []

    @pytest.mark.asyncio
    async def test_read_resource_no_servers(self):
        client = MCPClient()
        with pytest.raises(ValueError, match="No MCP server"):
            await client.read_resource("test://resource")

    @pytest.mark.asyncio
    async def test_close_empty(self):
        client = MCPClient()
        await client.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_call_tool_with_mock_session(self):
        client = MCPClient(server_urls=["http://localhost:5001"])

        # Mock the session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "search result"
        mock_result.content = [mock_content]
        mock_session.call_tool.return_value = mock_result
        mock_session.initialize = AsyncMock()

        client._sessions["http://localhost:5001"] = mock_session

        result = await client.call_tool("web_search", query="test")
        assert result == "search result"
        mock_session.call_tool.assert_called_once_with(
            "web_search", arguments={"query": "test"}
        )

    @pytest.mark.asyncio
    async def test_list_tools_with_mock_session(self):
        client = MCPClient(server_urls=["http://localhost:5001"])

        mock_session = AsyncMock()
        mock_tool = MagicMock()
        mock_tool.name = "web_search"
        mock_tool.description = "Search the web"
        mock_tool.inputSchema = {"type": "object"}
        mock_response = MagicMock()
        mock_response.tools = [mock_tool]
        mock_session.list_tools.return_value = mock_response

        client._sessions["http://localhost:5001"] = mock_session

        tools = await client.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "web_search"
        assert tools[0]["description"] == "Search the web"
        assert tools[0]["server_url"] == "http://localhost:5001"


class TestExtractMCPContent:
    def test_single_text_content(self):
        mock_result = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "hello"
        mock_result.content = [mock_content]
        assert _extract_mcp_content(mock_result) == "hello"

    def test_multiple_contents(self):
        mock_result = MagicMock()
        c1 = MagicMock()
        c1.text = "hello"
        c2 = MagicMock()
        c2.text = "world"
        mock_result.content = [c1, c2]
        result = _extract_mcp_content(mock_result)
        assert result == ["hello", "world"]

    def test_no_content_attr(self):
        result = _extract_mcp_content("plain string")
        assert result == "plain string"


class TestAgentMCPIntegration:
    def test_add_mcp_server(self):
        agent = Agent(name="Test", description="Test")
        agent.add_mcp_server("http://localhost:5001")
        assert "http://localhost:5001" in agent._mcp_servers

    def test_mcp_type_hint_detection(self):
        agent = Agent(name="Test", description="Test")
        agent.add_mcp_server("http://localhost:5001")

        @agent.skill("research")
        async def research(query: str, mcp: MCPClient) -> str:
            return "test"

        skill_def = agent._skills["research"]
        assert skill_def.needs_mcp is True
        assert skill_def.mcp_param == "mcp"

    def test_no_mcp_hint_means_no_injection(self):
        agent = Agent(name="Test", description="Test")

        @agent.skill("simple")
        async def simple(text: str) -> str:
            return text

        skill_def = agent._skills["simple"]
        assert skill_def.needs_mcp is False
        assert skill_def.mcp_param is None
