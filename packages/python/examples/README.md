# A2A Lite Examples

Progressive examples demonstrating A2A Lite features from simple to advanced.

## Examples

| # | File | Description | Features |
|---|------|-------------|----------|
| 01 | [01_hello_world.py](01_hello_world.py) | Minimal agent (8 lines) | Basic skill |
| 02 | [02_calculator.py](02_calculator.py) | Multiple skills with error handling | Multi-skill, error handling |
| 03 | [03_async_agent.py](03_async_agent.py) | Async operations | async/await |
| 04 | [04_multi_agent/](04_multi_agent/) | Multiple agents communicating | Remote calls |
| 05 | [05_with_llm.py](05_with_llm.py) | OpenAI integration | LLM, streaming |
| 06 | [06_pydantic_models.py](06_pydantic_models.py) | Pydantic model validation | Pydantic, schemas |
| 07 | [07_middleware.py](07_middleware.py) | Middleware chain | Logging, timing, retry |
| 08 | [08_streaming.py](08_streaming.py) | Streaming responses | Generators, SSE |
| 09 | [09_testing.py](09_testing.py) | Unit testing with AgentTestClient | Testing |
| 10 | [10_file_handling.py](10_file_handling.py) | File uploads and downloads | FilePart, DataPart |
| 11 | [11_task_tracking.py](11_task_tracking.py) | Progress updates for long tasks | TaskContext |
| 12 | [12_with_auth.py](12_with_auth.py) | API key and OAuth2 authentication | Auth |
| 13 | [13_mcp_tools.py](13_mcp_tools.py) | MCP tool integration | MCP, tool calling |
| 14 | [14_multi_agent_network.py](14_multi_agent_network.py) | AgentNetwork orchestration | Network, delegate |
| 15 | [15_llm_openai.py](15_llm_openai.py) | OpenAI-powered agent with streaming | LLM decorators |
| 16 | [16_llm_anthropic.py](16_llm_anthropic.py) | Anthropic-powered agent | LLM decorators |

## Running Examples

Each example is a standalone script:

```bash
cd packages/python

# Run any example
uv run examples/01_hello_world.py

# Test a running agent
a2a-lite test http://localhost:8787 hello -p name=World
```

## Prerequisites

Most examples only need the core `a2a-lite` package. Some require extras:

```bash
# For MCP tools (example 13)
pip install a2a-lite[mcp]

# For OpenAI (examples 05, 15)
pip install a2a-lite[openai]

# For Anthropic (example 16)
pip install a2a-lite[anthropic]
```
