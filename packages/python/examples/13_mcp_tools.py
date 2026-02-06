"""
Example 13: MCP Tool Integration

Demonstrates using MCP (Model Context Protocol) servers for tool calling.
Skills can request an MCPClient instance via type hints.

Prerequisites:
    pip install a2a-lite[mcp]
    # Have an MCP server running on localhost:5001

Run:
    python examples/13_mcp_tools.py
"""
from a2a_lite import Agent
from a2a_lite.mcp import MCPClient

agent = Agent(
    name="Research Agent",
    description="An agent that uses MCP tools for research",
    version="1.0.0",
)

# Register MCP servers
agent.add_mcp_server("http://localhost:5001")


@agent.skill("research", description="Research a topic using MCP tools")
async def research(query: str, mcp: MCPClient) -> str:
    """Use MCP tools to research a topic."""
    # List available tools
    tools = await mcp.list_tools()
    tool_names = [t["name"] for t in tools]

    # Call a search tool if available
    if "web_search" in tool_names:
        result = await mcp.call_tool("web_search", query=query)
        return f"Research results for '{query}': {result}"

    return f"No search tool available. Available tools: {tool_names}"


@agent.skill("list_tools", description="List available MCP tools")
async def list_tools(mcp: MCPClient) -> dict:
    """List all available MCP tools across servers."""
    tools = await mcp.list_tools()
    return {
        "tool_count": len(tools),
        "tools": [
            {"name": t["name"], "description": t["description"]}
            for t in tools
        ],
    }


if __name__ == "__main__":
    agent.run(port=8787)
