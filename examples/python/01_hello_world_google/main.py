"""
Hello World Agent - Google A2A Python SDK (Official)

A complete working example using the official a2a-sdk package.
This implements a simple greeting agent that responds to text messages.

Installation:
    pip install "a2a-sdk[http-server]"

Usage:
    python main.py

API Endpoints:
    GET  /.well-known/agent-card.json  - Agent capability description
    POST /                             - Send messages to the agent
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

import uvicorn
from a2a.server.apps.rest import A2ARESTFastAPIApplication
from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.events import InMemoryQueueManager
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.types import (
    AgentCard,
    AgentSkill,
    AgentCapabilities,
    Task,
    TaskStatus,
    TaskState,
    Message,
    TextPart,
    TaskStatusUpdateEvent,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# 1. AGENT CARD - Describes the agent's capabilities
# =============================================================================

AGENT_CARD = AgentCard(
    name="HelloAgent",
    description="A friendly greeting agent that responds to messages using Google A2A SDK",
    version="1.0.0",
    url="http://localhost:8787/",
    capabilities=AgentCapabilities(
        streaming=False,
        push_notifications=False,
        state_transition_history=False,
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
        
        Args:
            context: Contains the request message, task ID, and other metadata
            event_queue: Queue to publish events (task updates, artifacts)
        """
        task_id = context.task_id
        user_input = context.get_user_input()
        
        logger.info(f"Processing task {task_id}: user_input='{user_input}'")
        
        # Create the greeting response
        if user_input.strip():
            greeting_text = f"Hello! You said: '{user_input}'. Welcome to A2A! 👋"
        else:
            greeting_text = "Hello! I'm a friendly A2A agent. Send me a message! 👋"
        
        # Create a response message
        response_message = Message(
            role="agent",
            parts=[TextPart(text=greeting_text)],
            task_id=task_id,
            message_id=str(uuid.uuid4()),
        )
        
        # Create the completed task
        completed_task = Task(
            id=task_id,
            context_id=context.context_id or task_id,
            status=TaskStatus(
                state=TaskState.completed,
                timestamp=datetime.now(timezone.utc).isoformat(),
                message=response_message,
            ),
            history=[response_message],
        )
        
        # Publish the completed task to the event queue
        await event_queue.enqueue_event(completed_task)
        logger.info(f"Task {task_id} completed successfully")

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Handle task cancellation requests.
        
        Args:
            context: Contains the task ID to cancel
            event_queue: Queue to publish cancellation status
        """
        task_id = context.task_id
        logger.info(f"Cancelling task {task_id}")
        
        # Create a cancellation status update
        cancel_message = Message(
            role="agent",
            parts=[TextPart(text="Task was cancelled by user request.")],
            task_id=task_id,
            message_id=str(uuid.uuid4()),
        )
        
        cancelled_task = Task(
            id=task_id,
            context_id=context.context_id or task_id,
            status=TaskStatus(
                state=TaskState.canceled,
                timestamp=datetime.now(timezone.utc).isoformat(),
                message=cancel_message,
            ),
            history=[cancel_message],
        )
        
        await event_queue.enqueue_event(cancelled_task)
        logger.info(f"Task {task_id} cancelled")


# =============================================================================
# 3. SERVER SETUP - Initialize and run the A2A server
# =============================================================================

def create_app():
    """
    Create and configure the FastAPI application with A2A endpoints.
    
    Returns:
        Configured FastAPI application instance
    """
    # Create infrastructure components
    task_store = InMemoryTaskStore()
    queue_manager = InMemoryQueueManager()
    agent_executor = HelloAgentExecutor()
    
    # Create the request handler that coordinates all components
    handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=task_store,
        queue_manager=queue_manager,
    )
    
    # Create the REST API application
    app_builder = A2ARESTFastAPIApplication(
        agent_card=AGENT_CARD,
        http_handler=handler,
    )
    
    return app_builder.build()


def main():
    """Initialize and run the A2A agent server."""
    print("=" * 70)
    print("  Hello Agent - Google A2A Python SDK (Official)")
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
    print("    Send Message:    POST http://localhost:8787/")
    print("=" * 70)
    print("  Server starting on http://localhost:8787 ...")
    print("  Press Ctrl+C to stop")
    print("=" * 70)
    
    # Create the FastAPI app
    app = create_app()
    
    # Run the server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8787,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
