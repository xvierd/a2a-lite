"""
Tests for MCP Client resource cleanup (memory leak fix).
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestMCPClientCleanup:
    """Tests that MCPClient properly cleans up resources."""

    @pytest.mark.asyncio
    async def test_mcp_client_context_manager(self):
        """Test that MCPClient works as an async context manager."""
        from a2a_lite.mcp import MCPClient

        client = MCPClient(server_urls=["http://localhost:5001"])

        # Mock close to verify it's called
        client.close = AsyncMock()

        async with client as c:
            assert c is client

        # Verify close was called
        client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mcp_client_context_manager_exception(self):
        """Test that MCPClient closes even on exception."""
        from a2a_lite.mcp import MCPClient

        client = MCPClient(server_urls=["http://localhost:5001"])

        # Mock close to verify it's called
        client.close = AsyncMock()

        with pytest.raises(ValueError, match="Test error"):
            async with client:
                raise ValueError("Test error")

        # Verify close was called even with exception
        client.close.assert_awaited_once()

    def test_mcp_client_has_aenter_aexit(self):
        """Test that MCPClient has __aenter__ and __aexit__ methods."""
        from a2a_lite.mcp import MCPClient

        client = MCPClient()

        assert hasattr(client, '__aenter__')
        assert hasattr(client, '__aexit__')
        assert callable(client.__aenter__)
        assert callable(client.__aexit__)

    @pytest.mark.asyncio
    async def test_mcp_client_close_clears_sessions(self):
        """Test that close() clears all sessions."""
        from a2a_lite.mcp import MCPClient

        client = MCPClient(server_urls=["http://localhost:5001"])

        # Add a mock session
        mock_session = MagicMock()
        mock_session.close = AsyncMock()
        client._sessions["http://localhost:5001"] = mock_session

        await client.close()

        # Sessions should be cleared
        assert len(client._sessions) == 0
        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_agent_test_client_has_aenter_aexit(self):
        """Test that AsyncAgentTestClient has context manager support."""
        from a2a_lite.testing import AsyncAgentTestClient
        from a2a_lite import Agent

        agent = Agent(name="Test", description="Test")
        client = AsyncAgentTestClient(agent)

        # Check for context manager methods
        assert hasattr(client, '__aenter__')
        assert hasattr(client, '__aexit__')
        assert callable(client.__aenter__)
        assert callable(client.__aexit__)

    @pytest.mark.asyncio
    async def test_async_agent_test_client_context_manager(self):
        """Test AsyncAgentTestClient as context manager closes client."""
        from a2a_lite.testing import AsyncAgentTestClient
        from a2a_lite import Agent

        agent = Agent(name="Test", description="Test")
        client = AsyncAgentTestClient(agent)

        # Mock close method
        client.close = AsyncMock()

        async with client as c:
            assert c is client

        # Verify close was called
        client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_agent_test_client_context_manager_exception(self):
        """Test AsyncAgentTestClient closes on exception."""
        from a2a_lite.testing import AsyncAgentTestClient
        from a2a_lite import Agent

        agent = Agent(name="Test", description="Test")
        client = AsyncAgentTestClient(agent)

        # Mock close method
        client.close = AsyncMock()

        with pytest.raises(ValueError, match="Test error"):
            async with client:
                raise ValueError("Test error")

        # Verify close was called even with exception
        client.close.assert_awaited_once()
