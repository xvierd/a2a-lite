"""
Streaming Agent - Google A2A SDK Implementation (A2A v1.0)

Demonstrates Server-Sent Events (SSE) for real-time streaming responses
using the official a2a-sdk 1.x.

v1.0 streaming pattern (strictly enforced by the SDK):
  1. The FIRST event must be the Task itself.
  2. Every chunk goes out via TaskUpdater.update_status (or add_artifact).
  3. The stream ends with updater.complete() / failed() / cancel().
  Emitting multiple bare Messages raises InvalidAgentResponseError.

Install: pip install "a2a-sdk[http-server]>=1.1.2,<2.0"
"""

import asyncio
import json
import os

import uvicorn
from starlette.applications import Starlette

from a2a.helpers import new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    create_agent_card_routes,
    create_jsonrpc_routes,
    create_rest_routes,
)
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    TaskState,
)

from skills import chat_stream, count_stream, story_generator, progress_simulator

AGENT_URL = "http://localhost:8791/"


# =============================================================================
# Agent Card with Streaming Capabilities
# =============================================================================

AGENT_CARD = AgentCard(
    name="StreamingAgent",
    description="Agent with real-time streaming capabilities using SSE",
    version="1.0.0",
    supported_interfaces=[
        AgentInterface(
            url=AGENT_URL,
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        ),
    ],
    capabilities=AgentCapabilities(
        streaming=True,           # Enable streaming support
        push_notifications=False,
    ),
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    skills=[
        AgentSkill(
            id="chat",
            name="chat",
            description="Chat with word-by-word streaming response",
            tags=["chat", "streaming"],
        ),
        AgentSkill(
            id="count",
            name="count",
            description="Count numbers with progress streaming",
            tags=["count", "progress", "streaming"],
        ),
        AgentSkill(
            id="story",
            name="story",
            description="Generate story progressively with streaming",
            tags=["story", "creative", "streaming"],
        ),
        AgentSkill(
            id="progress",
            name="progress",
            description="Simulate task progress with streaming updates",
            tags=["progress", "simulation", "streaming"],
        ),
    ]
)


# =============================================================================
# Custom AgentExecutor with Streaming Support
# =============================================================================

class StreamingAgentExecutor(AgentExecutor):
    """
    Custom AgentExecutor that handles streaming skills.

    Each chunk produced by the skill generators is sent as a WORKING
    status update; the task is then completed. On the wire (SSE) every
    update is a `data: {"result": {"statusUpdate": ...}}` event.
    """

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Execute a skill based on the incoming request."""
        # 1. Enqueue the Task FIRST (strict v1.0 rule)
        task = context.current_task or new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            message = context.get_user_input()
            skill_name, params = self._parse_message(message)

            print(f"[StreamingAgent] Executing skill: {skill_name} with params: {params}")

            # 2. Transition to working
            await updater.start_work(
                message=updater.new_agent_message([
                    new_text_part(f"Starting {skill_name}...")
                ])
            )

            # 3. Run the streaming skill
            if skill_name == "chat":
                await self._stream(chat_stream(params.get("message", "Hello")), updater)
            elif skill_name == "count":
                await self._stream(
                    count_stream(
                        params.get("start", 1),
                        params.get("end", 10),
                        params.get("delay", 0.5),
                    ),
                    updater,
                )
            elif skill_name == "story":
                await self._stream(story_generator(params.get("theme", "adventure")), updater)
            elif skill_name == "progress":
                await self._stream(progress_simulator(params.get("task", "processing")), updater)
            else:
                await updater.failed(
                    message=updater.new_agent_message([new_text_part(json.dumps({
                        "error": f"Unknown skill: {skill_name}",
                        "available_skills": ["chat", "count", "story", "progress"],
                    }))])
                )
                return

            # 4. Complete the task
            await updater.complete(
                message=updater.new_agent_message([
                    new_text_part(f"{skill_name} finished")
                ])
            )

        except Exception as e:
            print(f"[StreamingAgent] Error: {e}")
            await updater.failed(
                message=updater.new_agent_message([new_text_part(json.dumps({
                    "error": str(e),
                    "type": type(e).__name__,
                }))])
            )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Handle cancellation requests."""
        print(f"[StreamingAgent] Cancelling task: {context.task_id}")
        task = context.current_task
        if task is not None:
            updater = TaskUpdater(event_queue, task.id, task.context_id)
            await updater.cancel(
                message=updater.new_agent_message([
                    new_text_part(json.dumps({"status": "cancelled"}))
                ])
            )

    def _parse_message(self, message: str) -> tuple:
        """Parse message to extract skill name and parameters."""
        try:
            data = json.loads(message)
            if isinstance(data, dict):
                if "skill" in data:
                    return data["skill"], data.get("params", {})
                return "chat", {"message": message}
        except json.JSONDecodeError:
            # Plain text message - use as chat
            return "chat", {"message": message}
        return "chat", {"message": message}

    async def _stream(self, chunk_generator, updater: TaskUpdater) -> None:
        """Forward every chunk as a WORKING status update (SSE event)."""
        async for chunk in chunk_generator:
            await updater.update_status(
                TaskState.TASK_STATE_WORKING,
                message=updater.new_agent_message([
                    new_text_part(json.dumps(chunk))
                ]),
            )


# =============================================================================
# Main Entry Point
# =============================================================================

def create_app() -> Starlette:
    """Create and configure the A2A Starlette application."""
    task_store = InMemoryTaskStore()
    agent_executor = StreamingAgentExecutor()

    handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=task_store,
        agent_card=AGENT_CARD,
    )

    return Starlette(
        routes=create_agent_card_routes(AGENT_CARD)
        + create_jsonrpc_routes(handler, rpc_url="/")
        + create_rest_routes(handler)
    )


def main():
    """Initialize and run the streaming A2A agent."""
    print("=" * 70)
    print("Streaming Agent - Google A2A Python SDK (REAL API) - A2A v1.0")
    print("=" * 70)
    print(f"Agent: {AGENT_CARD.name}")
    print(f"Description: {AGENT_CARD.description}")
    print(f"Version: {AGENT_CARD.version}")
    print(f"Streaming: {AGENT_CARD.capabilities.streaming}")
    print("-" * 70)
    print("Streaming Skills:")
    for skill in AGENT_CARD.skills:
        print(f"  • {skill.name}: {skill.description}")
    print("-" * 70)
    print("Endpoints:")
    print("  • Agent Card: http://localhost:8791/.well-known/agent-card.json")
    print("  • JSON-RPC:   http://localhost:8791/")
    print("=" * 70)
    print("\nTest with:")
    print("""  curl -N -X POST http://localhost:8791/ \\
    -H "Content-Type: application/json" \\
    -H "A2A-Version: 1.0" \\
    -H "Accept: text/event-stream" \\
    -d '{"jsonrpc":"2.0","method":"SendStreamingMessage","id":"1","params":{"message":{"role":"ROLE_USER","messageId":"m1","parts":[{"text":"{\\"skill\\":\\"chat\\",\\"params\\":{\\"message\\":\\"Hello\\"}}"}]}}}'""")

    app = create_app()
    port = int(os.getenv("PORT", "8791"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
