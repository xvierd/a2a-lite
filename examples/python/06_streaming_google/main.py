"""
Streaming Agent - Google A2A SDK Implementation (REAL API)

Demonstrates Server-Sent Events (SSE) for real-time streaming responses
using the official Google A2A Python SDK with A2ARESTFastAPIApplication.

Install: pip install "a2a-sdk[http-server]"
"""

import asyncio
import json
import uvicorn

from a2a.server.apps.rest import A2ARESTFastAPIApplication
from a2a.types import AgentCard, AgentSkill, AgentCapabilities
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.events.in_memory_queue_manager import InMemoryQueueManager
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.utils import new_agent_text_message

from skills import chat_stream, count_stream, story_generator, progress_simulator


# =============================================================================
# Agent Card with Streaming Capabilities
# =============================================================================

AGENT_CARD = AgentCard(
    name="StreamingAgent",
    description="Agent with real-time streaming capabilities using SSE",
    version="1.0.0",
    url="http://localhost:8791/",
    capabilities=AgentCapabilities(
        streaming=True,           # Enable streaming support
        pushNotifications=False,
    ),
    defaultInputModes=["text"],
    defaultOutputModes=["text"],
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
    
    The execute() method receives events through the event_queue for streaming.
    Each yielded chunk from the skill generators is sent as a separate SSE event.
    """
    
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Execute a skill based on the incoming request.
        
        Args:
            context: Request context containing message, task info, etc.
            event_queue: Event queue for streaming responses via SSE
        """
        try:
            # Extract message from context
            message = ""
            if hasattr(context, "message") and context.message:
                msg = context.message
                if hasattr(msg, "parts"):
                    for part in msg.parts:
                        if hasattr(part, "text"):
                            message = part.text
                            break
                        elif isinstance(part, dict) and part.get("type") == "text":
                            message = part.get("text", "")
                            break
            
            # Parse skill call from message
            skill_name, params = self._parse_message(message)
            
            print(f"[StreamingAgent] Executing skill: {skill_name} with params: {params}")
            
            # Execute the appropriate streaming skill
            if skill_name == "chat":
                await self._stream_chat(params, event_queue)
            elif skill_name == "count":
                await self._stream_count(params, event_queue)
            elif skill_name == "story":
                await self._stream_story(params, event_queue)
            elif skill_name == "progress":
                await self._stream_progress(params, event_queue)
            else:
                # Unknown skill - return error
                error_msg = json.dumps({
                    "error": f"Unknown skill: {skill_name}",
                    "available_skills": ["chat", "count", "story", "progress"]
                })
                await event_queue.enqueue_event(new_agent_text_message(error_msg))
                
        except Exception as e:
            print(f"[StreamingAgent] Error: {e}")
            error_msg = json.dumps({
                "error": str(e),
                "type": type(e).__name__
            })
            await event_queue.enqueue_event(new_agent_text_message(error_msg))
    
    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Handle cancellation requests."""
        print(f"[StreamingAgent] Cancelling task: {context.task_id}")
        await event_queue.enqueue_event(
            new_agent_text_message(json.dumps({"status": "cancelled"}))
        )
    
    def _parse_message(self, message: str) -> tuple:
        """Parse message to extract skill name and parameters."""
        try:
            data = json.loads(message)
            if isinstance(data, dict):
                if "skill" in data:
                    return data["skill"], data.get("params", {})
                # If no explicit skill, try to infer from content
                return None, {"message": message}
        except json.JSONDecodeError:
            # Plain text message - use as chat
            return "chat", {"message": message}
        return None, {}
    
    # =============================================================================
    # Streaming Skill Handlers
    # =============================================================================
    
    async def _stream_chat(self, params: dict, event_queue: EventQueue) -> None:
        """Stream chat responses word by word."""
        message = params.get("message", "Hello")
        
        async for chunk in chat_stream(message):
            await event_queue.enqueue_event(
                new_agent_text_message(json.dumps(chunk))
            )
    
    async def _stream_count(self, params: dict, event_queue: EventQueue) -> None:
        """Stream count numbers with progress."""
        start = params.get("start", 1)
        end = params.get("end", 10)
        delay = params.get("delay", 0.5)
        
        async for chunk in count_stream(start, end, delay):
            await event_queue.enqueue_event(
                new_agent_text_message(json.dumps(chunk))
            )
    
    async def _stream_story(self, params: dict, event_queue: EventQueue) -> None:
        """Stream story parts progressively."""
        theme = params.get("theme", "adventure")
        
        async for chunk in story_generator(theme):
            await event_queue.enqueue_event(
                new_agent_text_message(json.dumps(chunk))
            )
    
    async def _stream_progress(self, params: dict, event_queue: EventQueue) -> None:
        """Stream task progress updates."""
        task = params.get("task", "processing")
        
        async for chunk in progress_simulator(task):
            await event_queue.enqueue_event(
                new_agent_text_message(json.dumps(chunk))
            )


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Initialize and run the streaming A2A agent."""
    
    # Create infrastructure components
    task_store = InMemoryTaskStore()
    queue_manager = InMemoryQueueManager()
    agent_executor = StreamingAgentExecutor()
    
    print("=" * 70)
    print("Streaming Agent - Google A2A Python SDK (REAL API)")
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
    print("  • API: http://localhost:8791/")
    print("=" * 70)
    print("\nTest with:")
    print("""  curl -N -X POST http://localhost:8791/ \\
    -H "Content-Type: application/json" \\
    -H "Accept: text/event-stream" \\
    -d '{"jsonrpc":"2.0","method":"message/send","id":"1","params":{"message":{"role":"user","parts":[{"type":"text","text":"{\\"skill\\":\\"chat\\",\\"params\\":{\\"message\\":\\"Hello\\"}}"}]}}}'""")
    
    # Create request handler with streaming support
    handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=task_store,
        queue_manager=queue_manager
    )
    
    # Build FastAPI application with A2A streaming endpoints
    app = A2ARESTFastAPIApplication(
        agent_card=AGENT_CARD,
        http_handler=handler
    ).build()
    
    # Run the server
    uvicorn.run(app, host="0.0.0.0", port=8791)


if __name__ == "__main__":
    main()
