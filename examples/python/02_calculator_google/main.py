"""
Calculator Agent - Google A2A Python SDK (Official), A2A protocol v1.0

A complete working example demonstrating:
- AgentCard with multiple skills (add, subtract, multiply, divide, power)
- Custom AgentExecutor with the v1.0 task pattern:
  Task first, then TaskUpdater (status updates, data artifacts, complete/fail)
- Cancellation support
- Server assembled from route factories (create_agent_card_routes,
  create_jsonrpc_routes, create_rest_routes)

Usage:
    pip install -r requirements.txt
    python main.py

The server will start on http://localhost:8788
"""

import asyncio
import json
import logging
import os
import uuid

import uvicorn
from starlette.applications import Starlette

from a2a.helpers import new_task_from_user_message
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

AGENT_URL = "http://localhost:8788/"


# =============================================================================
# Calculator Operations
# =============================================================================

class CalculatorError(Exception):
    """Exception for calculator execution errors."""
    pass


def add(a: float, b: float) -> dict:
    """Add two numbers."""
    return {"result": a + b}


def subtract(a: float, b: float) -> dict:
    """Subtract b from a."""
    return {"result": a - b}


def multiply(a: float, b: float) -> dict:
    """Multiply two numbers."""
    return {"result": a * b}


def divide(a: float, b: float) -> dict:
    """Divide a by b."""
    if b == 0:
        raise CalculatorError("Division by zero is not allowed")
    return {"result": a / b, "remainder": a % b}


def power(base: float, exponent: float) -> dict:
    """Raise base to the power of exponent."""
    return {"result": base ** exponent}


# Skill registry mapping skill IDs to functions
SKILL_REGISTRY = {
    "add": add,
    "subtract": subtract,
    "multiply": multiply,
    "divide": divide,
    "power": power,
}


# =============================================================================
# Agent Card Definition
# =============================================================================

AGENT_CARD = AgentCard(
    name="CalculatorAgent",
    description="A calculator agent with arithmetic operations",
    version="1.0.0",
    supported_interfaces=[
        AgentInterface(
            url=AGENT_URL,
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        ),
    ],
    capabilities=AgentCapabilities(
        streaming=True,
        push_notifications=False,
    ),
    default_input_modes=["text/plain", "application/json"],
    default_output_modes=["text/plain", "application/json"],
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

    v1.0 task pattern (strictly enforced by the SDK):
      1. The FIRST event must be the Task itself.
      2. All subsequent events go through TaskUpdater:
         start_work -> update_status/add_artifact -> complete/failed/cancel.
    """

    def __init__(self):
        self._cancelled_tasks: set[str] = set()
        self._lock = asyncio.Lock()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute the agent's logic for a given request context."""
        # 1. Create (or resume) the task and enqueue it FIRST
        task = context.current_task or new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)

        # 2. TaskUpdater wraps the queue for this task
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        logger.info("Executing task %s", task.id)

        user_input = context.get_user_input().strip()

        # Parse the input as JSON
        try:
            request_data = json.loads(user_input)
        except json.JSONDecodeError:
            await updater.failed(
                message=updater.new_agent_message([_text_part(
                    'Invalid JSON input. Expected: {"skill": "add", "params": {"a": 1, "b": 2}}'
                )])
            )
            return

        # Extract skill and parameters
        skill_id = request_data.get("skill")
        params = request_data.get("params", {})

        if skill_id not in SKILL_REGISTRY:
            available = ", ".join(SKILL_REGISTRY.keys())
            await updater.failed(
                message=updater.new_agent_message([_text_part(
                    f"Unknown skill: '{skill_id}'. Available skills: {available}"
                )])
            )
            return

        async with self._lock:
            if task.id in self._cancelled_tasks:
                await updater.cancel()
                return

        # 3. Transition to working with a status message
        await updater.start_work(
            message=updater.new_agent_message([_text_part(f"Executing {skill_id}...")])
        )

        # Execute the skill
        try:
            result = SKILL_REGISTRY[skill_id](**params)
        except TypeError as e:
            await updater.failed(
                message=updater.new_agent_message([_text_part(
                    f"Invalid parameters for '{skill_id}': {e}"
                )])
            )
            return
        except CalculatorError as e:
            await updater.failed(
                message=updater.new_agent_message([_text_part(str(e))])
            )
            return

        async with self._lock:
            if task.id in self._cancelled_tasks:
                await updater.cancel()
                return

        # 4. Publish the result as a data artifact
        await updater.add_artifact(
            [_data_part(result)],
            name="result",
        )

        # 5. Mark the task completed
        await updater.complete(
            message=updater.new_agent_message([_text_part(
                f"Completed {skill_id} successfully"
            )])
        )

        logger.info("Task %s completed successfully", task.id)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Request the agent to cancel an ongoing task."""
        task_id = context.task_id
        if not task_id:
            logger.warning("Cancel requested but no task_id provided")
            return

        logger.info("Cancelling task %s", task_id)

        async with self._lock:
            self._cancelled_tasks.add(task_id)

        # If the task is still running, execute() will observe the flag and
        # cancel via TaskUpdater. Emit a cancelled update if a task exists.
        task = context.current_task
        if task is not None:
            updater = TaskUpdater(event_queue, task.id, task.context_id)
            await updater.cancel()

        logger.info("Task %s cancelled", task_id)


# =============================================================================
# Part helpers (v1.0: single Part type with oneof content)
# =============================================================================

def _text_part(text: str):
    from a2a.helpers import new_text_part
    return new_text_part(text)


def _data_part(data: dict):
    from a2a.helpers import new_data_part
    return new_data_part(data)


# =============================================================================
# Server Setup
# =============================================================================

def create_app() -> Starlette:
    """Create and configure the A2A Starlette application."""
    task_store = InMemoryTaskStore()
    agent_executor = CalculatorExecutor()

    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=task_store,
        agent_card=AGENT_CARD,
    )

    return Starlette(
        routes=create_agent_card_routes(AGENT_CARD)
        + create_jsonrpc_routes(request_handler, rpc_url="/")
        + create_rest_routes(request_handler)
    )


def main():
    """Run the calculator agent server."""
    print("=" * 70)
    print("Calculator Agent - Google A2A Python SDK (Official) - A2A v1.0")
    print("=" * 70)
    print(f"Agent: {AGENT_CARD.name}")
    print(f"Version: {AGENT_CARD.version}")
    print(f"Skills: {[s.id for s in AGENT_CARD.skills]}")
    print("-" * 70)
    print("Starting server on http://localhost:8788")
    print("Agent Card: http://localhost:8788/.well-known/agent-card.json")
    print("=" * 70)
    print()
    print("Example usage:")
    print('  curl -X POST http://localhost:8788/ \\')
    print('    -H "Content-Type: application/json" \\')
    print('    -H "A2A-Version: 1.0" \\')
    print('    -d \'{"jsonrpc": "2.0", "method": "SendMessage", "id": "1", "params": {"message": {"role": "ROLE_USER", "messageId": "msg-1", "parts": [{"text": "{\\"skill\\": \\"add\\", \\"params\\": {\\"a\\": 10, \\"b\\": 5}}"}]}}}\'')
    print()

    app = create_app()
    port = int(os.getenv("PORT", "8788"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
