"""
MCP (Model Context Protocol) tool integration for A2A Lite.

Wraps the official ``mcp`` Python SDK to let skills call MCP tools.

Requires: pip install a2a-lite[mcp]

Example:
    agent.add_mcp_server("http://localhost:5001")

    @agent.skill("research")
    async def research(query: str, mcp: MCPClient) -> str:
        result = await mcp.call_tool("web_search", query=query)
        return result
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for interacting with MCP servers.

    Provides a simplified interface to call tools, list tools, and
    read resources from one or more MCP servers.

    Args:
        server_urls: List of MCP server URLs to connect to.

    Example:
        mcp = MCPClient(server_urls=["http://localhost:5001"])
        result = await mcp.call_tool("web_search", query="A2A protocol")
        tools = await mcp.list_tools()
    """

    def __init__(self, server_urls: Optional[List[str]] = None) -> None:
        self._server_urls: List[str] = list(server_urls) if server_urls else []
        self._sessions: Dict[str, Any] = {}

    def add_server(self, url: str) -> None:
        """Add an MCP server URL.

        Args:
            url: The MCP server URL.
        """
        self._server_urls.append(url)

    async def _get_session(self, url: str) -> Any:
        """Get or create an MCP client session for a server URL.

        Args:
            url: The MCP server URL.

        Returns:
            An MCP ClientSession instance.

        Raises:
            ImportError: If the ``mcp`` package is not installed.
        """
        if url in self._sessions:
            return self._sessions[url]

        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client
        except ImportError:
            raise ImportError(
                "MCP integration requires the 'mcp' package. "
                "Install it with: pip install a2a-lite[mcp]"
            )

        read_stream, write_stream = sse_client(url)
        session = ClientSession(read_stream, write_stream)
        await session.initialize()
        self._sessions[url] = session
        return session

    async def call_tool(
        self,
        tool_name: str,
        server_url: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """Call an MCP tool by name.

        If ``server_url`` is provided, calls that specific server.
        Otherwise searches all registered servers for the tool.

        Args:
            tool_name: The name of the MCP tool to call.
            server_url: Optional specific server URL to use.
            **kwargs: Arguments to pass to the tool.

        Returns:
            The tool's result content.

        Raises:
            ValueError: If the tool is not found on any server.
            ImportError: If the ``mcp`` package is not installed.
        """
        urls = [server_url] if server_url else self._server_urls

        for url in urls:
            try:
                session = await self._get_session(url)
                result = await session.call_tool(tool_name, arguments=kwargs)
                return _extract_mcp_content(result)
            except Exception as e:
                if "not found" in str(e).lower() or "unknown tool" in str(e).lower():
                    continue
                raise

        raise ValueError(
            f"Tool '{tool_name}' not found on any MCP server. Servers: {urls}"
        )

    async def list_tools(
        self,
        server_url: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List available tools from MCP servers.

        Args:
            server_url: If provided, list tools from this server only.

        Returns:
            List of tool descriptors with name, description, and input schema.
        """
        urls = [server_url] if server_url else self._server_urls
        all_tools: List[Dict[str, Any]] = []

        for url in urls:
            try:
                session = await self._get_session(url)
                response = await session.list_tools()
                for tool in response.tools:
                    all_tools.append(
                        {
                            "name": tool.name,
                            "description": getattr(tool, "description", ""),
                            "input_schema": getattr(tool, "inputSchema", {}),
                            "server_url": url,
                        }
                    )
            except ImportError:
                raise
            except Exception:
                logger.warning("Failed to list tools from %s", url, exc_info=True)

        return all_tools

    async def read_resource(
        self,
        uri: str,
        server_url: Optional[str] = None,
    ) -> Any:
        """Read a resource from an MCP server.

        Args:
            uri: The resource URI to read.
            server_url: If provided, read from this server only.

        Returns:
            The resource content.
        """
        url = server_url or (self._server_urls[0] if self._server_urls else None)
        if url is None:
            raise ValueError("No MCP server URLs configured")

        session = await self._get_session(url)
        result = await session.read_resource(uri)
        return result

    async def close(self) -> None:
        """Close all MCP sessions."""
        for url, session in self._sessions.items():
            try:
                await session.close()
            except Exception:
                logger.warning("Error closing MCP session for %s", url, exc_info=True)
        self._sessions.clear()

    def __repr__(self) -> str:
        return f"MCPClient(servers={self._server_urls})"


def _extract_mcp_content(result: Any) -> Any:
    """Extract content from an MCP tool result.

    Args:
        result: The raw MCP CallToolResult.

    Returns:
        The extracted content as a string or list.
    """
    if hasattr(result, "content"):
        contents = result.content
        if len(contents) == 1:
            item = contents[0]
            if hasattr(item, "text"):
                return item.text
            return item
        return [c.text if hasattr(c, "text") else c for c in contents]
    return result
