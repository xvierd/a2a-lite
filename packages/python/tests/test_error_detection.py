"""
Tests for error detection - verifies errors are detected without fragile string matching.
"""
import pytest
from unittest.mock import MagicMock, patch


class TestErrorDetection:
    """Tests that errors are detected using proper types, not string matching."""

    def test_orchestration_detects_json_rpc_error_key(self):
        """Test that orchestration._extract_result detects JSON-RPC error by key presence."""
        from a2a_lite.orchestration import _extract_result

        # Error response
        error_response = {
            "jsonrpc": "2.0",
            "id": "123",
            "error": {"code": -32600, "message": "Invalid Request"}
        }

        result = _extract_result(error_response)
        assert result == {"code": -32600, "message": "Invalid Request"}

    def test_orchestration_returns_success_result(self):
        """Test that orchestration._extract_result returns result when no error."""
        from a2a_lite.orchestration import _extract_result

        # Success response
        success_response = {
            "jsonrpc": "2.0",
            "id": "123",
            "result": {"parts": [{"type": "text", "text": "Hello"}]}
        }

        result = _extract_result(success_response)
        assert result == "Hello"

    def test_testing_client_detects_error_key(self):
        """Test that testing client detects error by key presence."""
        from a2a_lite.testing import AgentTestClient, TestClientError

        # Create a mock to test _extract_result directly
        client = MagicMock()
        client._extract_result = AgentTestClient._extract_result.__get__(client, MagicMock)

        # Error response should raise TestClientError
        error_response = {
            "jsonrpc": "2.0",
            "id": "123",
            "error": {"code": -32600, "message": "Invalid Request"}
        }

        with pytest.raises(TestClientError) as exc_info:
            client._extract_result(error_response)

        assert "Invalid Request" in str(exc_info.value)

    def test_mcp_call_tool_not_found_handling(self):
        """Test that MCP call_tool properly handles 'not found' errors."""
        from a2a_lite.mcp import MCPClient

        client = MCPClient(server_urls=["http://localhost:5001"])

        # Mock _get_session to simulate a tool not found error
        class ToolNotFoundError(Exception):
            pass

        async def mock_get_session(url):
            raise ToolNotFoundError("Tool 'search' not found on server")

        client._get_session = mock_get_session

        import asyncio

        # Should raise ValueError after trying all servers
        with pytest.raises(ValueError, match="Tool 'search' not found on any MCP server"):
            asyncio.run(client.call_tool("search"))

    def test_error_detection_not_using_substring_matching(self):
        """Verify that 'error' in dict checks key existence, not substring."""
        # This test documents that Python's `key in dict` checks for key existence
        # not substring matching, which is the correct behavior

        response_with_error_key = {"error": "some error", "data": "value"}
        response_without_error = {"result": "success", "data": "value"}
        response_with_error_in_value = {"message": "error occurred", "data": "value"}
        response_with_error_in_key_name = {"error_details": "info", "data": "value"}

        # All these should be True only if 'error' key exists
        assert "error" in response_with_error_key  # True - has 'error' key
        assert "error" not in response_without_error  # False - no 'error' key
        assert "error" not in response_with_error_in_value  # False - 'error' is in value, not key
        assert "error" not in response_with_error_in_key_name  # False - 'error_details' != 'error'

    def test_json_rpc_error_response_structure(self):
        """Test handling of standard JSON-RPC error response structure."""
        from a2a_lite.testing import AgentTestClient, TestClientError

        # Standard JSON-RPC error response
        json_rpc_error = {
            "jsonrpc": "2.0",
            "id": "test-id",
            "error": {
                "code": -32602,
                "message": "Invalid params",
                "data": {"details": "Missing required field"}
            }
        }

        # Should be detected as error and raise TestClientError
        with pytest.raises(TestClientError):
            AgentTestClient._extract_result(MagicMock(), json_rpc_error)


class TestMCPToolNotFoundDetection:
    """Tests for MCPClient._is_tool_not_found_error method."""

    def test_detects_tool_not_found_by_exception_type(self):
        """Test detection by exception type name."""
        from a2a_lite.mcp import MCPClient

        client = MCPClient()

        class ToolNotFoundError(Exception):
            pass

        assert client._is_tool_not_found_error(ToolNotFoundError("test")) is True

    def test_detects_by_error_code_attribute(self):
        """Test detection by error.code attribute."""
        from a2a_lite.mcp import MCPClient

        client = MCPClient()

        class CodedError(Exception):
            code = "TOOL_NOT_FOUND"

        assert client._is_tool_not_found_error(CodedError("test")) is True

    def test_detects_by_json_rpc_method_not_found(self):
        """Test detection of JSON-RPC method not found code."""
        from a2a_lite.mcp import MCPClient

        client = MCPClient()

        class JsonRpcError(Exception):
            code = -32601

        assert client._is_tool_not_found_error(JsonRpcError("test")) is True

    def test_detects_by_specific_message_patterns(self):
        """Test detection by specific message patterns."""
        from a2a_lite.mcp import MCPClient

        client = MCPClient()

        # Test various specific patterns
        patterns = [
            "unknown tool",
            "tool not found",
            "tool 'search' is missing",
            'tool "calc" does not exist',
            "no tool named 'test'",
        ]

        for pattern in patterns:
            assert client._is_tool_not_found_error(Exception(pattern)) is True, f"Failed for: {pattern}"

    def test_generic_not_found_requires_tool_mention(self):
        """Test that generic 'not found' requires 'tool' in message."""
        from a2a_lite.mcp import MCPClient

        client = MCPClient()

        # Should NOT match - no tool mentioned
        assert client._is_tool_not_found_error(Exception("file not found")) is False
        assert client._is_tool_not_found_error(Exception("server not found")) is False

        # Should match - tool mentioned
        assert client._is_tool_not_found_error(Exception("tool not found")) is True
        assert client._is_tool_not_found_error(Exception("Tool xyz not found")) is True

    def test_other_errors_not_detected_as_tool_not_found(self):
        """Test that other errors are not falsely detected."""
        from a2a_lite.mcp import MCPClient

        client = MCPClient()

        # These should NOT be detected as tool not found
        other_errors = [
            Exception("connection timeout"),
            Exception("authentication failed"),
            Exception("server error"),
            ValueError("invalid parameter"),
            RuntimeError("something went wrong"),
        ]

        for error in other_errors:
            assert client._is_tool_not_found_error(error) is False, f"Failed for: {error}"
