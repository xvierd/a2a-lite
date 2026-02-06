# Examples

A2A Lite includes 16 progressive examples. Each is a standalone script.

## Running Examples

```bash
cd packages/python

# Run any example
uv run examples/01_hello_world.py

# Test a running agent
a2a-lite test http://localhost:8787 hello -p name=World
```

## Example Index

### Basics

| # | Example | Description |
|---|---------|-------------|
| 01 | `01_hello_world.py` | Minimal 8-line agent |
| 02 | `02_calculator.py` | Multiple skills, error handling |
| 03 | `03_async_agent.py` | Async operations |

### Intermediate

| # | Example | Description |
|---|---------|-------------|
| 04 | `04_multi_agent/` | Multiple agents communicating |
| 05 | `05_with_llm.py` | OpenAI integration (manual) |
| 06 | `06_pydantic_models.py` | Pydantic input validation |
| 07 | `07_middleware.py` | Middleware chain patterns |
| 08 | `08_streaming.py` | Generator-based streaming |

### Testing & Files

| # | Example | Description |
|---|---------|-------------|
| 09 | `09_testing.py` | AgentTestClient unit testing |
| 10 | `10_file_handling.py` | FilePart uploads/downloads |
| 11 | `11_task_tracking.py` | TaskContext progress updates |
| 12 | `12_with_auth.py` | API key & OAuth2 auth |

### Advanced

| # | Example | Description | Extra Dep |
|---|---------|-------------|-----------|
| 13 | `13_mcp_tools.py` | MCP tool integration | `[mcp]` |
| 14 | `14_multi_agent_network.py` | AgentNetwork orchestration | — |
| 15 | `15_llm_openai.py` | OpenAI decorator with streaming | `[openai]` |
| 16 | `16_llm_anthropic.py` | Anthropic decorator | `[anthropic]` |
