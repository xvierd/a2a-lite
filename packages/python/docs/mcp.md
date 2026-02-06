# MCP Tool Integration

A2A Lite integrates with [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) servers, letting your skills call external tools.

## Installation

```bash
pip install a2a-lite[mcp]
```

## Quick Start

```python
from a2a_lite import Agent
from a2a_lite.mcp import MCPClient

agent = Agent(name="Research Agent", description="Uses MCP tools")

# Register MCP servers
agent.add_mcp_server("http://localhost:5001")

@agent.skill("research")
async def research(query: str, mcp: MCPClient) -> str:
    result = await mcp.call_tool("web_search", query=query)
    return result
```

## How It Works

1. Register MCP servers with `agent.add_mcp_server(url)`
2. Add `mcp: MCPClient` type hint to your skill function
3. A2A Lite automatically injects an `MCPClient` instance
4. Use `mcp.call_tool()`, `mcp.list_tools()`, `mcp.read_resource()`

## MCPClient API

### `call_tool(tool_name, server_url=None, **kwargs)`

Call an MCP tool by name. If no `server_url` is specified, searches all registered servers.

```python
result = await mcp.call_tool("web_search", query="A2A protocol")
result = await mcp.call_tool("calculator", server_url="http://math:5001", expression="2+2")
```

### `list_tools(server_url=None)`

List available tools from all servers (or a specific one).

```python
tools = await mcp.list_tools()
for tool in tools:
    print(f"{tool['name']}: {tool['description']}")
```

### `read_resource(uri, server_url=None)`

Read a resource from an MCP server.

```python
content = await mcp.read_resource("file:///docs/readme.md")
```

## Multiple Servers

You can register multiple MCP servers. `call_tool` will search all of them:

```python
agent.add_mcp_server("http://localhost:5001")  # Search tools
agent.add_mcp_server("http://localhost:5002")  # Database tools

@agent.skill("research")
async def research(query: str, mcp: MCPClient) -> str:
    # Automatically finds the right server
    web_result = await mcp.call_tool("web_search", query=query)
    db_result = await mcp.call_tool("query_db", sql="SELECT ...")
    return f"{web_result}\n{db_result}"
```

## Example

See [`examples/13_mcp_tools.py`](https://github.com/a2a-lite/a2a-lite/blob/main/packages/python/examples/13_mcp_tools.py) for a complete working example.
