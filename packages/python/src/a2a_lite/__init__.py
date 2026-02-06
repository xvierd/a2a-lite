"""
A2A Lite - Build A2A agents in 8 lines. Add enterprise features when you need them.

SIMPLE (8 lines):
    from a2a_lite import Agent

    agent = Agent(name="Bot", description="A bot")

    @agent.skill("greet")
    async def greet(name: str) -> str:
        return f"Hello, {name}!"

    agent.run()

TEST IT (3 lines):
    from a2a_lite import AgentTestClient
    client = AgentTestClient(agent)
    assert client.call("greet", name="World") == "Hello, World!"

WITH PYDANTIC:
    class User(BaseModel):
        name: str

    @agent.skill("create")
    async def create(user: User) -> dict:
        return {"created": user.name}

WITH STREAMING:
    @agent.skill("chat", streaming=True)
    async def chat(msg: str):
        for word in msg.split():
            yield word

WITH AUTH (opt-in):
    from a2a_lite.auth import APIKeyAuth
    agent = Agent(name="Bot", auth=APIKeyAuth(keys=["secret"]))

WITH TASK TRACKING (opt-in):
    from a2a_lite.tasks import TaskContext

    @agent.skill("process")
    async def process(data: str, task: TaskContext) -> str:
        await task.update("working", progress=0.5)
        return "done"

WITH FILES (opt-in):
    from a2a_lite.parts import FilePart

    @agent.skill("summarize")
    async def summarize(doc: FilePart) -> str:
        text = await doc.read_text()
        return summarize(text)

WITH MCP TOOLS (opt-in):
    from a2a_lite import MCPClient

    agent.add_mcp_server("http://localhost:5001")

    @agent.skill("research")
    async def research(query: str, mcp: MCPClient) -> str:
        result = await mcp.call_tool("web_search", query=query)
        return result

WITH MULTI-AGENT (opt-in):
    from a2a_lite import AgentNetwork

    network = AgentNetwork()
    network.add("weather", "http://weather:8787")
    agent = Agent(name="Planner", description="...", network=network)
"""

# Core
from .agent import Agent
from .decorators import SkillDefinition
from .testing import AgentTestClient, AsyncAgentTestClient, TestResult

# Middleware
from .middleware import (
    MiddlewareContext,
    MiddlewareChain,
    logging_middleware,
    timing_middleware,
    retry_middleware,
    rate_limit_middleware,
)

# Parts (multi-modal)
from .parts import TextPart, FilePart, DataPart, Artifact

# Tasks
from .tasks import TaskContext, TaskState, TaskStatus, Task, TaskStore

# Auth
from .auth import (
    AuthProvider,
    AuthResult,
    NoAuth,
    APIKeyAuth,
    BearerAuth,
    OAuth2Auth,
    require_auth,
)

# Errors
from .errors import (
    A2ALiteError,
    SkillNotFoundError,
    ParamValidationError,
    AuthRequiredError,
)

# Orchestration
from .orchestration import AgentNetwork

# MCP (requires optional dep)
from .mcp import MCPClient

__version__ = "0.2.5"

__all__ = [
    # Core
    "Agent",
    "SkillDefinition",
    # Testing
    "AgentTestClient",
    "AsyncAgentTestClient",
    "TestResult",
    # Middleware
    "MiddlewareContext",
    "MiddlewareChain",
    "logging_middleware",
    "timing_middleware",
    "retry_middleware",
    "rate_limit_middleware",
    # Parts (multi-modal)
    "TextPart",
    "FilePart",
    "DataPart",
    "Artifact",
    # Tasks
    "TaskContext",
    "TaskState",
    "TaskStatus",
    "Task",
    "TaskStore",
    # Auth
    "AuthProvider",
    "AuthResult",
    "NoAuth",
    "APIKeyAuth",
    "BearerAuth",
    "OAuth2Auth",
    "require_auth",
    # Errors
    "A2ALiteError",
    "SkillNotFoundError",
    "ParamValidationError",
    "AuthRequiredError",
    # Orchestration
    "AgentNetwork",
    # MCP
    "MCPClient",
]
