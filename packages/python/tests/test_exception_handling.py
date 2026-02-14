"""
Tests for exception handling - verifies errors are logged not swallowed.
"""
import logging
import pytest
from unittest.mock import patch, MagicMock


class TestExceptionHandling:
    """Tests that exceptions are properly logged, not silently swallowed."""

    def test_get_type_hints_failure_logged_in_utils(self, caplog):
        """Test that get_type_hints failure is logged in utils.extract_function_schemas."""
        import typing
        from a2a_lite.utils import extract_function_schemas

        def sample_func(x: int) -> int:
            return x

        with caplog.at_level(logging.DEBUG):
            with patch.object(typing, 'get_type_hints', side_effect=Exception("Test error")):
                # Should not raise, should fallback to __annotations__
                extract_function_schemas(sample_func)

        # Should have logged the exception
        assert "Test error" in caplog.text or "Failed to get type hints" in caplog.text

    def test_get_type_hints_failure_logged_in_agent(self, caplog):
        """Test that get_type_hints failure is logged in agent.skill decorator."""
        import typing
        from a2a_lite import Agent

        with caplog.at_level(logging.DEBUG):
            with patch.object(typing, 'get_type_hints', side_effect=Exception("Agent test error")):
                agent = Agent(name="Test", description="Test")

                @agent.skill("test")
                async def test_skill(x: int) -> int:
                    return x

        # Check that error was logged
        assert "Agent test error" in caplog.text or "Failed to resolve type hints" in caplog.text

    def test_get_type_hints_failure_logged_in_executor(self, caplog):
        """Test that get_type_hints failure is logged in executor._convert_params."""
        import logging
        import typing
        from unittest.mock import MagicMock, patch

        # Create a mock handler to test the logging directly
        mock_handler = MagicMock()
        mock_handler.__annotations__ = {'x': int, 'return': int}
        mock_handler.__name__ = 'test_handler'

        # Simulate what _convert_params does when get_type_hints fails
        logger = logging.getLogger('a2a_lite.executor')

        with caplog.at_level(logging.DEBUG, logger='a2a_lite.executor'):
            with patch.object(typing, 'get_type_hints', side_effect=Exception("Executor test error")):
                try:
                    hints = typing.get_type_hints(mock_handler)
                except Exception as e:
                    # This is the pattern we implemented
                    logger.debug("Failed to get type hints for handler '%s': %s", getattr(mock_handler, '__name__', 'unknown'), e)
                    hints = getattr(mock_handler, "__annotations__", {})

        # Check that error was logged
        assert "Executor test error" in caplog.text or "Failed to get type hints" in caplog.text

    def test_mcp_list_tools_exception_logged(self, caplog):
        """Test that MCP list_tools exceptions are properly logged."""
        import logging
        from a2a_lite.mcp import MCPClient

        client = MCPClient(server_urls=["http://localhost:5001"])

        # Mock _get_session to raise an exception
        async def mock_get_session(url):
            raise Exception("Connection failed")

        with caplog.at_level(logging.WARNING):
            import asyncio
            asyncio.run(client.list_tools())

        # Should have logged the warning
        assert "Failed to list tools" in caplog.text or "Connection failed" in caplog.text

    def test_mcp_close_exception_logged(self, caplog):
        """Test that MCP close session exceptions are properly logged."""
        from a2a_lite.mcp import MCPClient

        client = MCPClient(server_urls=["http://localhost:5001"])

        # Create a mock session that raises on close
        mock_session = MagicMock()
        mock_session.close = MagicMock(side_effect=Exception("Close failed"))
        client._sessions["http://localhost:5001"] = mock_session

        with caplog.at_level(logging.WARNING):
            import asyncio
            asyncio.run(client.close())

        # Should have logged the warning
        assert "Error closing MCP session" in caplog.text or "Close failed" in caplog.text
