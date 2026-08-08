"""
Hello World Agent - Google A2A Python SDK (Official), A2A protocol v1.0

A complete working example using the official a2a-sdk package (1.1.x).
This implements a simple greeting agent that responds to text messages.

Key 1.x changes vs 0.3:
- The 0.3 application builders were removed; the server
  is assembled from route factories (create_agent_card_routes,
  create_jsonrpc_routes, create_rest_routes) on a plain Starlette app.
- Types are protobuf messages (snake_case kwargs), not pydantic models.
- Non-streaming executors respond with a single Message via
  a2a.helpers.new_text_message().

Installation:
    pip install "a2a-sdk[http-server]>=1.1.2,<2.0"

Usage:
    python main.py

API Endpoints:
    GET  /.well-known/agent-card.json  - Agent capability description
    POST /                             - JSON-RPC (SendMessage)
    POST /message:send                 - REST (HTTP+JSON) binding
"""

import logging

import uvicorn
from starlette.applications import Starlette

from a2a.helpers import new_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    create_agent_card_routes,
    create_jsonrpc_routes,
    create_rest_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

AGENT_URL = "http://localhost:8787/"


# =============================================================================
# 1. AGENT CARD - Describes the agent's capabilities
# =============================================================================

AGENT_CARD = AgentCard(
    name="HelloAgent",
    description="A friendly greeting agent that responds to messages using Google A2A SDK",
    version="1.0.0",
    # v1.0: no top-level url; endpoints are declared per protocol binding
    supported_interfaces=[
        AgentInterface(
            url=AGENT_URL,
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        ),
        AgentInterface(
            url=AGENT_URL,
            protocol_binding="HTTP+JSON",
            protocol_version="1.0",
        ),
    ],
    capabilities=AgentCapabilities(
        streaming=False,
        push_notifications=False,
    ),
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    skills=[
        AgentSkill(
            id="greet",
            name="Greeting",
            description="Responds with a friendly greeting message",
            tags=["greeting", "hello", "welcome"],
        )
    ],
)


# =============================================================================
# 2. AGENT EXECUTOR - Core logic implementation
# =============================================================================

class HelloAgentExecutor(AgentExecutor):
    """
    Agent executor that implements the greeting logic.

    The execute() method is called when a new message arrives.
    The cancel() method is called when a task needs to be cancelled.
    """

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Process the incoming message and generate a response.

        Non-streaming rule (strictly enforced by the SDK): emit exactly ONE
        Message event and nothing else.
        """
        user_input = context.get_user_input()
        logger.info("Processing message: user_input=%r", user_input)

        # Create the greeting response
        if user_input.strip():
            greeting_text = f"Hello! You said: '{user_input}'. Welcome to A2A! 👋"
        else:
            greeting_text = "Hello! I'm a friendly A2A agent. Send me a message! 👋"

        # Publish the single response message
        await event_queue.enqueue_event(new_text_message(greeting_text))
        logger.info("Response sent")

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Handle task cancellation requests.

        This agent never starts a long-running task, so cancellation is a no-op.
        """
        logger.info("Cancel requested for task %s (no-op)", context.task_id)


# =============================================================================
# 3. SERVER SETUP - Initialize and run the A2A server
# =============================================================================

def create_app() -> Starlette:
    """
    Create and configure the Starlette application with A2A endpoints.

    v1.0 pattern: route factories instead of the removed
    0.3 application builders.
    """
    task_store = InMemoryTaskStore()
    agent_executor = HelloAgentExecutor()

    # The request handler coordinates executor, task store and agent card
    handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=task_store,
        agent_card=AGENT_CARD,
    )

    # Assemble the app from route factories:
    # - well-known agent card
    # - JSON-RPC endpoint at "/"
    # - REST (HTTP+JSON) endpoints: /message:send, /tasks/{id}, ...
    return Starlette(
        routes=create_agent_card_routes(AGENT_CARD)
        + create_jsonrpc_routes(handler, rpc_url="/")
        + create_rest_routes(handler)
    )


def main():
    """Initialize and run the A2A agent server."""
    print("=" * 70)
    print("  Hello Agent - Google A2A Python SDK (Official) - A2A v1.0")
    print("=" * 70)
    print(f"  Agent Name:        {AGENT_CARD.name}")
    print(f"  Description:       {AGENT_CARD.description}")
    print(f"  Version:           {AGENT_CARD.version}")
    print(f"  Skills:            {', '.join(s.name for s in AGENT_CARD.skills)}")
    print(f"  Input Modes:       {', '.join(AGENT_CARD.default_input_modes)}")
    print(f"  Output Modes:      {', '.join(AGENT_CARD.default_output_modes)}")
    print("-" * 70)
    print("  Endpoints:")
    print("    Agent Card:      http://localhost:8787/.well-known/agent-card.json")
    print("    JSON-RPC:        POST http://localhost:8787/")
    print("    REST:            POST http://localhost:8787/message:send")
    print("=" * 70)
    print("  Server starting on http://localhost:8787 ...")
    print("  Press Ctrl+C to stop")
    print("=" * 70)

    app = create_app()

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8787,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
