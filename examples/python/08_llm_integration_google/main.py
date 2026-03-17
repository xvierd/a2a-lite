"""
LLM Agent - Google A2A SDK Implementation (REAL API)

Advanced agent with OpenAI/Anthropic integration, conversation memory,
and tool calling capabilities using the official Google A2A SDK.
"""

import os
import json
import asyncio
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

import uvicorn
from dotenv import load_dotenv

# Google A2A SDK imports
from a2a.server.apps.rest import A2ARESTFastAPIApplication
from a2a.types import (
    AgentCard, AgentSkill, AgentCapabilities,
    Message, TextPart, TaskState
)
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.events.in_memory_queue_manager import InMemoryQueueManager
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler

# Local imports
from llm_client import LLMClient
from conversation import ConversationManager
from tools import ToolRegistry, handle_tool_calls

# Load environment variables
load_dotenv()

# Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL = os.getenv("LLM_MODEL", None)


# Create Agent Card with LLM capabilities
AGENT_CARD = AgentCard(
    name="LLMAgent",
    description="AI agent powered by OpenAI/Anthropic LLM with memory and tools",
    version="1.0.0",
    url="http://localhost:8792/",
    capabilities=AgentCapabilities(
        streaming=True,
        pushNotifications=False,
        stateTransitionHistory=True
    ),
    default_input_modes=["text"],
    default_output_modes=["text"],
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
    - Chat with conversation memory
    - Tool calling (calculator, weather, time, search)
    - Memory management
    - Info queries
    """
    
    def __init__(self):
        self.conversation_mgr = ConversationManager(max_history=10)
        self.tool_registry = ToolRegistry()
        self.llm_client: Optional[LLMClient] = None
        
        # Initialize LLM client
        try:
            self.llm_client = LLMClient(provider=LLM_PROVIDER, model=LLM_MODEL)
            print(f"✓ LLM Client initialized: {LLM_PROVIDER}")
        except ValueError as e:
            print(f"✗ LLM Client initialization failed: {e}")
    
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Execute the agent logic based on the request context.
        
        This is the main entry point called by the A2A SDK.
        """
        task = context.task
        session_id = task.sessionId or "default"
        
        # Extract skill call from the message
        skill_call = self._extract_skill_call(task.message)
        
        if not skill_call:
            await self._send_error(event_queue, task.id, "No skill call found in message")
            return
        
        skill_name = skill_call.get("skill")
        skill_params = skill_call.get("params", {})
        
        try:
            if skill_name == "chat":
                await self._handle_chat(task.id, session_id, skill_params, event_queue)
            elif skill_name == "clear_memory":
                await self._handle_clear_memory(task.id, session_id, event_queue)
            elif skill_name == "info":
                await self._handle_info(task.id, event_queue)
            else:
                await self._send_error(event_queue, task.id, f"Unknown skill: {skill_name}")
        except Exception as e:
            await self._send_error(event_queue, task.id, f"Error executing skill: {str(e)}")
    
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel a running task (not implemented for this agent)."""
        print(f"Cancel requested for task: {context.task.id}")
    
    def _extract_skill_call(self, message: Optional[Message]) -> Optional[Dict]:
        """Extract skill call from A2A message."""
        if not message or not message.parts:
            return None
        
        for part in message.parts:
            if hasattr(part, 'text'):
                try:
                    return json.loads(part.text)
                except json.JSONDecodeError:
                    # If not JSON, treat as direct chat message
                    return {"skill": "chat", "params": {"message": part.text}}
        return None
    
    async def _handle_chat(
        self, 
        task_id: str, 
        session_id: str, 
        params: Dict, 
        event_queue: EventQueue
    ) -> None:
        """Handle chat skill with LLM integration."""
        if not self.llm_client:
            await self._send_error(event_queue, task_id, 
                "LLM client not configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY.")
            return
        
        user_message = params.get("message", "")
        if not user_message:
            await self._send_error(event_queue, task_id, "No message provided")
            return
        
        # Add user message to history
        self.conversation_mgr.add_message(session_id, "user", user_message)
        
        # Get conversation history
        messages = self.conversation_mgr.get_messages(session_id)
        
        # Get available tools
        available_tools = self.tool_registry.get_schemas()
        
        # Send status update
        await event_queue.send_status_update(
            task_id=task_id,
            state=TaskState.WORKING,
            message="Processing with LLM..."
        )
        
        # Call LLM
        response = await self.llm_client.chat(
            messages=messages,
            tools=available_tools
        )
        
        # Handle tool calls if present
        if "tool_calls" in response:
            tool_results = handle_tool_calls(response["tool_calls"], self.tool_registry)
            
            # Add assistant message with tool calls
            self.conversation_mgr.add_message(
                session_id,
                "assistant",
                response.get("content", ""),
                {"tool_calls": response["tool_calls"]}
            )
            
            # Add tool results
            for result in tool_results:
                self.conversation_mgr.add_message(
                    session_id,
                    "user",
                    result["content"],
                    {"tool_result": True, "name": result["name"]}
                )
            
            # Send status update
            await event_queue.send_status_update(
                task_id=task_id,
                state=TaskState.WORKING,
                message="Processing tool results..."
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
        
        # Send final response
        result = {
            "response": response["content"],
            "session_id": session_id,
            "history_length": len(self.conversation_mgr.get_or_create_session(session_id))
        }
        
        await self._send_success(event_queue, task_id, result)
    
    async def _handle_clear_memory(
        self, 
        task_id: str, 
        session_id: str, 
        event_queue: EventQueue
    ) -> None:
        """Handle clear_memory skill."""
        self.conversation_mgr.clear_session(session_id)
        
        result = {
            "message": "Memory cleared",
            "session_id": session_id
        }
        
        await self._send_success(event_queue, task_id, result)
    
    async def _handle_info(self, task_id: str, event_queue: EventQueue) -> None:
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
        
        await self._send_success(event_queue, task_id, result)
    
    async def _send_success(
        self, 
        event_queue: EventQueue, 
        task_id: str, 
        result: Dict
    ) -> None:
        """Send success response via event queue."""
        message = Message(
            role="agent",
            parts=[TextPart(text=json.dumps(result))]
        )
        
        await event_queue.send_task_completed(
            task_id=task_id,
            message=message
        )
    
    async def _send_error(
        self, 
        event_queue: EventQueue, 
        task_id: str, 
        error_message: str
    ) -> None:
        """Send error response via event queue."""
        await event_queue.send_task_completed(
            task_id=task_id,
            message=Message(
                role="agent",
                parts=[TextPart(text=json.dumps({"error": error_message}))]
            )
        )


def main():
    """Initialize and run the LLM Agent."""
    print("=" * 70)
    print("LLM Agent - Google A2A SDK (REAL API)")
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
    
    # Create components
    task_store = InMemoryTaskStore()
    queue_manager = InMemoryQueueManager()
    agent_executor = LLMAgentExecutor()
    
    # Create request handler
    handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=task_store,
        queue_manager=queue_manager
    )
    
    # Create FastAPI application
    app = A2ARESTFastAPIApplication(
        agent_card=AGENT_CARD,
        http_handler=handler
    ).build()
    
    print("Starting server on http://localhost:8792")
    print("Agent card: http://localhost:8792/.well-known/agent-card.json")
    print("=" * 70)
    
    # Run server
    uvicorn.run(app, host="0.0.0.0", port=8792)


if __name__ == "__main__":
    main()
