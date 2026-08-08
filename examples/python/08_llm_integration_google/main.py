"""
LLM Agent - Google A2A SDK Implementation (A2A v1.0)

Advanced agent with OpenAI/Anthropic integration, conversation memory,
and tool calling capabilities using the official a2a-sdk 1.x.

v1.0 notes:
- The server is assembled from route factories (the 0.3 app builders were removed).
- The executor uses the task pattern: Task first, then TaskUpdater.
- There is no task.sessionId in v1.0: the conversation key is the
  request's context_id (stable across messages of the same conversation).

Setup:
    pip install -r requirements.txt
    export OPENAI_API_KEY=...      # or ANTHROPIC_API_KEY
    python main.py

The agent starts even without API keys: the "chat" skill then reports a
clear configuration error, while "info" and "clear_memory" keep working.
"""

import json
import os
from typing import Dict, Optional

import uvicorn
from starlette.applications import Starlette

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv is optional; env vars can be set directly
    pass

# Google A2A SDK imports (1.x)
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

# Local imports
from llm_client import LLMClient
from conversation import ConversationManager
from tools import tools as default_tool_registry, handle_tool_calls

# Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL = os.getenv("LLM_MODEL", None)

AGENT_URL = "http://localhost:8792/"


# Create Agent Card with LLM capabilities
AGENT_CARD = AgentCard(
    name="LLMAgent",
    description="AI agent powered by OpenAI/Anthropic LLM with memory and tools",
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
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    skills=[
        AgentSkill(
            id="chat",
            name="chat",
            description="Chat with the AI assistant. Supports multi-turn conversations with memory.",
            tags=["conversation", "llm", "chat"],
            examples=[
                "What is the capital of France?",
                "Calculate 25 * 47",
                "What is my name? (remembers context)"
            ]
        ),
        AgentSkill(
            id="clear_memory",
            name="clear_memory",
            description="Clear conversation memory for a session",
            tags=["memory", "reset"],
            examples=["Clear my conversation history"]
        ),
        AgentSkill(
            id="info",
            name="info",
            description="Get information about the agent capabilities and configuration",
            tags=["info", "metadata"],
            examples=["What can you do?", "What tools do you have?"]
        )
    ]
)


class LLMAgentExecutor(AgentExecutor):
    """
    Custom AgentExecutor that integrates with LLM APIs.

    Handles:
    - Chat with conversation memory (keyed by A2A context_id)
    - Tool calling (calculator, weather, time, search)
    - Memory management
    - Info queries
    """

    def __init__(self):
        self.conversation_mgr = ConversationManager(max_history=10)
        self.tool_registry = default_tool_registry
        self.llm_client: Optional[LLMClient] = None

        # Initialize LLM client (optional - agent starts without keys)
        try:
            self.llm_client = LLMClient(provider=LLM_PROVIDER, model=LLM_MODEL)
            print(f"✓ LLM Client initialized: {LLM_PROVIDER}")
        except ValueError as e:
            print(f"✗ LLM Client initialization failed: {e}")

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Execute the agent logic based on the request context.

        v1.0 task pattern: enqueue the Task first, then use TaskUpdater.
        """
        task = context.current_task or new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        # v1.0: the conversation/session key is the A2A context_id
        session_id = task.context_id or "default"

        skill_call = self._extract_skill_call(context)
        if not skill_call:
            await updater.failed(
                message=updater.new_agent_message([
                    new_text_part(json.dumps({"error": "No skill call found in message"}))
                ])
            )
            return

        skill_name = skill_call.get("skill")
        skill_params = skill_call.get("params", {})

        try:
            if skill_name == "chat":
                await self._handle_chat(session_id, skill_params, updater)
            elif skill_name == "clear_memory":
                await self._handle_clear_memory(session_id, updater)
            elif skill_name == "info":
                await self._handle_info(updater)
            else:
                await updater.failed(
                    message=updater.new_agent_message([
                        new_text_part(json.dumps({"error": f"Unknown skill: {skill_name}"}))
                    ])
                )
        except Exception as e:
            await updater.failed(
                message=updater.new_agent_message([
                    new_text_part(json.dumps({"error": f"Error executing skill: {e}"}))
                ])
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel a running task."""
        task = context.current_task
        if task is not None:
            updater = TaskUpdater(event_queue, task.id, task.context_id)
            await updater.cancel()

    def _extract_skill_call(self, context: RequestContext) -> Optional[Dict]:
        """Extract skill call from the request message."""
        user_input = context.get_user_input()
        if not user_input:
            return None

        try:
            return json.loads(user_input)
        except json.JSONDecodeError:
            # If not JSON, treat as direct chat message
            return {"skill": "chat", "params": {"message": user_input}}

    async def _handle_chat(
        self,
        session_id: str,
        params: Dict,
        updater: TaskUpdater,
    ) -> None:
        """Handle chat skill with LLM integration."""
        if not self.llm_client:
            await updater.failed(
                message=updater.new_agent_message([new_text_part(json.dumps({
                    "error": "LLM client not configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY.",
                }))])
            )
            return

        user_message = params.get("message", "")
        if not user_message:
            await updater.failed(
                message=updater.new_agent_message([
                    new_text_part(json.dumps({"error": "No message provided"}))
                ])
            )
            return

        # Add user message to history
        self.conversation_mgr.add_message(session_id, "user", user_message)

        # Get conversation history and available tools
        messages = self.conversation_mgr.get_messages(session_id)
        available_tools = self.tool_registry.get_schemas()

        # Status update while the LLM works
        await updater.update_status(
            TaskState.TASK_STATE_WORKING,
            message=updater.new_agent_message([
                new_text_part("Processing with LLM...")
            ]),
        )

        # Call LLM
        response = await self.llm_client.chat(
            messages=messages,
            tools=available_tools
        )

        # Handle tool calls if present
        if "tool_calls" in response:
            tool_results = handle_tool_calls(response["tool_calls"], self.tool_registry)

            # Add assistant message with tool calls + tool results to history
            self.conversation_mgr.add_message(
                session_id,
                "assistant",
                response.get("content", ""),
                {"tool_calls": response["tool_calls"]}
            )
            for result in tool_results:
                self.conversation_mgr.add_message(
                    session_id,
                    "user",
                    result["content"],
                    {"tool_result": True, "name": result["name"]}
                )

            await updater.update_status(
                TaskState.TASK_STATE_WORKING,
                message=updater.new_agent_message([
                    new_text_part("Processing tool results...")
                ]),
            )

            # Get final response from LLM with tool results
            messages = self.conversation_mgr.get_messages(session_id)
            response = await self.llm_client.chat(messages=messages)

        # Add assistant response to history
        self.conversation_mgr.add_message(
            session_id,
            "assistant",
            response["content"]
        )

        # Complete with the final response as a data artifact
        result = {
            "response": response["content"],
            "session_id": session_id,
            "history_length": len(self.conversation_mgr.get_or_create_session(session_id))
        }

        await updater.add_artifact([_data_part(result)], name="response")
        await updater.complete(
            message=updater.new_agent_message([new_text_part(response["content"])])
        )

    async def _handle_clear_memory(
        self,
        session_id: str,
        updater: TaskUpdater,
    ) -> None:
        """Handle clear_memory skill."""
        self.conversation_mgr.clear_session(session_id)

        await updater.complete(
            message=updater.new_agent_message([new_text_part(json.dumps({
                "message": "Memory cleared",
                "session_id": session_id,
            }))])
        )

    async def _handle_info(self, updater: TaskUpdater) -> None:
        """Handle info skill."""
        result = {
            "name": AGENT_CARD.name,
            "description": AGENT_CARD.description,
            "version": AGENT_CARD.version,
            "llm_provider": LLM_PROVIDER,
            "llm_model": self.llm_client.model if self.llm_client else "not configured",
            "llm_ready": self.llm_client is not None,
            "skills": [skill.name for skill in AGENT_CARD.skills],
            "tools_available": [tool["function"]["name"] for tool in self.tool_registry.get_schemas()],
            "features": ["memory", "tool_calling", "multi_turn", "streaming"]
        }

        await updater.complete(
            message=updater.new_agent_message([new_text_part(json.dumps(result, indent=2))])
        )


def _data_part(data: dict):
    from a2a.helpers import new_data_part
    return new_data_part(data)


def create_app() -> Starlette:
    """Create and configure the A2A Starlette application."""
    task_store = InMemoryTaskStore()
    agent_executor = LLMAgentExecutor()

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
    """Initialize and run the LLM Agent."""
    print("=" * 70)
    print("LLM Agent - Google A2A SDK (REAL API) - A2A v1.0")
    print("=" * 70)
    print(f"Agent: {AGENT_CARD.name}")
    print(f"Description: {AGENT_CARD.description}")
    print(f"Skills: {[s.name for s in AGENT_CARD.skills]}")
    print("-" * 70)
    print("Configuration:")
    print(f"  Provider: {LLM_PROVIDER}")
    print(f"  Model: {LLM_MODEL or 'default'}")
    print(f"  Port: 8792")
    print("-" * 70)
    print("Starting server on http://localhost:8792")
    print("Agent card: http://localhost:8792/.well-known/agent-card.json")
    print("=" * 70)

    app = create_app()
    port = int(os.getenv("PORT", "8792"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
