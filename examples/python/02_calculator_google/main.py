"""
Calculator Agent - Google A2A Python SDK (Official)

A complete working example demonstrating:
- AgentCard with multiple skills (add, subtract, multiply, divide, power)
- Custom AgentExecutor implementation with execute() and cancel()
- TaskStore, QueueManager, DefaultRequestHandler
- A2ARESTFastAPIApplication

Usage:
    pip install -r requirements.txt
    python main.py

The server will start on http://localhost:8788
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import uvicorn
from a2a.server.apps.rest import A2ARESTFastAPIApplication
from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue, InMemoryQueueManager
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    Artifact,
    DataPart,
    Message,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Calculator Operations
# =============================================================================

class CalculatorError(Exception):
    """Exception for calculator execution errors."""
    pass


def add(a: float, b: float) -> dict[str, Any]:
    """Add two numbers."""
    return {"result": a + b}


def subtract(a: float, b: float) -> dict[str, Any]:
    """Subtract b from a."""
    return {"result": a - b}


def multiply(a: float, b: float) -> dict[str, Any]:
    """Multiply two numbers."""
    return {"result": a * b}


def divide(a: float, b: float) -> dict[str, Any]:
    """Divide a by b."""
    if b == 0:
        raise CalculatorError("Division by zero is not allowed")
    return {"result": a / b, "remainder": a % b}


def power(base: float, exponent: float) -> dict[str, Any]:
    """Raise base to the power of exponent."""
    return {"result": base ** exponent}


# Skill registry mapping skill IDs to functions and parameter names
SKILL_REGISTRY = {
    "add": {"func": add, "params": ["a", "b"]},
    "subtract": {"func": subtract, "params": ["a", "b"]},
    "multiply": {"func": multiply, "params": ["a", "b"]},
    "divide": {"func": divide, "params": ["a", "b"]},
    "power": {"func": power, "params": ["base", "exponent"]},
}


# =============================================================================
# Agent Card Definition
# =============================================================================

AGENT_CARD = AgentCard(
    name="CalculatorAgent",
    description="A calculator agent with arithmetic operations",
    url="http://localhost:8788/",
    version="1.0.0",
    capabilities=AgentCapabilities(
        streaming=True,
        pushNotifications=False,
    ),
    defaultInputModes=["text", "text/plain", "application/json"],
    defaultOutputModes=["text", "text/plain", "application/json"],
    skills=[
        AgentSkill(
            id="add",
            name="Addition",
            description="Add two numbers together",
            tags=["math", "arithmetic", "addition"],
        ),
        AgentSkill(
            id="subtract",
            name="Subtraction",
            description="Subtract one number from another",
            tags=["math", "arithmetic", "subtraction"],
        ),
        AgentSkill(
            id="multiply",
            name="Multiplication",
            description="Multiply two numbers together",
            tags=["math", "arithmetic", "multiplication"],
        ),
        AgentSkill(
            id="divide",
            name="Division",
            description="Divide one number by another",
            tags=["math", "arithmetic", "division"],
        ),
        AgentSkill(
            id="power",
            name="Power",
            description="Raise a number to a power",
            tags=["math", "arithmetic", "exponentiation"],
        ),
    ],
)


# =============================================================================
# Custom Agent Executor
# =============================================================================

class CalculatorExecutor(AgentExecutor):
    """
    Custom AgentExecutor that handles calculator operations.
    
    Implements execute() and cancel() methods as required by the AgentExecutor interface.
    """

    def __init__(self):
        self._cancelled_tasks: set[str] = set()
        self._lock = asyncio.Lock()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Execute the agent's logic for a given request context.
        
        Args:
            context: The request context containing the message, task ID, etc.
            event_queue: The queue to publish events to.
        """
        task_id = context.task_id
        if not task_id:
            task_id = str(uuid.uuid4())
        
        context_id = context.context_id or str(uuid.uuid4())
        
        logger.info(f"Executing task {task_id}")
        
        # Get user input from the message
        user_input = context.get_user_input().strip()
        
        try:
            # Parse the input as JSON
            try:
                request_data = json.loads(user_input)
            except json.JSONDecodeError:
                await self._send_error(
                    event_queue, task_id, context_id,
                    "Invalid JSON input. Expected: {\"skill\": \"add\", \"params\": {\"a\": 1, \"b\": 2}}"
                )
                return
            
            # Extract skill and parameters
            skill_id = request_data.get("skill")
            params = request_data.get("params", {})
            
            # Validate skill
            if skill_id not in SKILL_REGISTRY:
                available = ", ".join(SKILL_REGISTRY.keys())
                await self._send_error(
                    event_queue, task_id, context_id,
                    f"Unknown skill: '{skill_id}'. Available skills: {available}"
                )
                return
            
            # Check if task was cancelled
            async with self._lock:
                if task_id in self._cancelled_tasks:
                    await self._send_cancelled(event_queue, task_id, context_id)
                    return
            
            # Send "working" status update
            await self._send_status_update(
                event_queue, task_id, context_id, TaskState.working,
                f"Executing {skill_id}..."
            )
            
            # Execute the skill
            skill_info = SKILL_REGISTRY[skill_id]
            try:
                result = skill_info["func"](**params)
            except TypeError as e:
                await self._send_error(
                    event_queue, task_id, context_id,
                    f"Invalid parameters for '{skill_id}': {str(e)}"
                )
                return
            except CalculatorError as e:
                await self._send_error(
                    event_queue, task_id, context_id, str(e)
                )
                return
            
            # Check if task was cancelled during execution
            async with self._lock:
                if task_id in self._cancelled_tasks:
                    await self._send_cancelled(event_queue, task_id, context_id)
                    return
            
            # Send the result as an artifact
            await self._send_result(event_queue, task_id, context_id, result)
            
            # Send "completed" status update
            await self._send_status_update(
                event_queue, task_id, context_id, TaskState.completed,
                f"Completed {skill_id} successfully", final=True
            )
            
            logger.info(f"Task {task_id} completed successfully")
            
        except Exception as e:
            logger.exception(f"Error executing task {task_id}")
            await self._send_error(
                event_queue, task_id, context_id,
                f"Internal error: {str(e)}"
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Request the agent to cancel an ongoing task.
        
        Args:
            context: The request context containing the task ID to cancel.
            event_queue: The queue to publish the cancellation status update to.
        """
        task_id = context.task_id
        if not task_id:
            logger.warning("Cancel requested but no task_id provided")
            return
        
        logger.info(f"Cancelling task {task_id}")
        
        async with self._lock:
            self._cancelled_tasks.add(task_id)
        
        context_id = context.context_id or str(uuid.uuid4())
        
        # Send cancelled status update
        await self._send_status_update(
            event_queue, task_id, context_id, TaskState.canceled,
            "Task cancelled by user request", final=True
        )
        
        logger.info(f"Task {task_id} cancelled")

    async def _send_status_update(
        self,
        event_queue: EventQueue,
        task_id: str,
        context_id: str,
        state: TaskState,
        message_text: str,
        final: bool = False
    ) -> None:
        """Send a status update event to the queue."""
        message = Message(
            message_id=str(uuid.uuid4()),
            role="agent",
            parts=[TextPart(text=message_text)],
        )
        status = TaskStatus(state=state, message=message)
        event = TaskStatusUpdateEvent(
            id=task_id,
            context_id=context_id,
            status=status,
            final=final,
        )
        await event_queue.enqueue_event(event)

    async def _send_result(
        self,
        event_queue: EventQueue,
        task_id: str,
        context_id: str,
        result: dict[str, Any]
    ) -> None:
        """Send the result as an artifact update event."""
        artifact = Artifact(
            artifact_id=str(uuid.uuid4()),
            description="Calculator operation result",
            parts=[DataPart(data=result)],
        )
        event = TaskArtifactUpdateEvent(
            id=task_id,
            context_id=context_id,
            artifact=artifact,
        )
        await event_queue.enqueue_event(event)

    async def _send_error(
        self,
        event_queue: EventQueue,
        task_id: str,
        context_id: str,
        error_message: str
    ) -> None:
        """Send an error status update."""
        logger.error(f"Task {task_id} error: {error_message}")
        await self._send_status_update(
            event_queue, task_id, context_id, TaskState.failed,
            error_message, final=True
        )

    async def _send_cancelled(
        self,
        event_queue: EventQueue,
        task_id: str,
        context_id: str
    ) -> None:
        """Send a cancelled status update."""
        await self._send_status_update(
            event_queue, task_id, context_id, TaskState.canceled,
            "Task was cancelled", final=True
        )


# =============================================================================
# Server Setup
# =============================================================================

def create_app():
    """Create and configure the A2A REST FastAPI application."""
    
    # Create the task store (in-memory for this example)
    task_store = InMemoryTaskStore()
    
    # Create the queue manager
    queue_manager = InMemoryQueueManager()
    
    # Create the custom agent executor
    agent_executor = CalculatorExecutor()
    
    # Create the request handler
    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=task_store,
        queue_manager=queue_manager,
    )
    
    # Create the A2A REST FastAPI application
    app_builder = A2ARESTFastAPIApplication(
        agent_card=AGENT_CARD,
        http_handler=request_handler,
    )
    
    return app_builder.build()


def main():
    """Run the calculator agent server."""
    print("=" * 70)
    print("Calculator Agent - Google A2A Python SDK (Official)")
    print("=" * 70)
    print(f"Agent: {AGENT_CARD.name}")
    print(f"Version: {AGENT_CARD.version}")
    print(f"Skills: {[s.id for s in AGENT_CARD.skills]}")
    print("-" * 70)
    print("Starting server on http://localhost:8788")
    print("Agent Card: http://localhost:8788/.well-known/agent.json")
    print("=" * 70)
    print()
    print("Example usage:")
    print('  curl -X POST http://localhost:8788/ \\')
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"jsonrpc": "2.0", "method": "tasks/send", "id": "1", "params": {"message": {"role": "user", "parts": [{"type": "text", "text": "{\\"skill\\": \\"add\\", \\"params\\": {\\"a\\": 10, \\"b\\": 5}"}], "messageId": "msg-1"}}}\'')
    print()
    
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8788)


if __name__ == "__main__":
    main()
