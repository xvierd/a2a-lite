#!/usr/bin/env python3
"""
File Handling Agent - Google A2A SDK Implementation

Demonstrates file upload/download handling using the REAL Google A2A SDK.
Uses AgentCard, AgentExecutor, and proper A2A types (FilePart, DataPart, etc.)
"""

import asyncio
import json
import uuid
from typing import Any, Dict

import uvicorn

from a2a.types import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    AgentProvider,
    Task,
    TaskState,
    TaskStatus,
    Message,
    Part,
    TextPart,
    FilePart,
    DataPart,
    Role,
    Artifact,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.apps.jsonrpc import A2AFastAPIApplication
from a2a.server.tasks import InMemoryTaskStore

from skills import (
    analyze_file,
    convert_to_upper,
    generate_report,
    extract_file_from_part,
    create_file_part,
    create_text_part,
    create_data_part,
    FileProcessingError,
)


# =============================================================================
# Agent Card Configuration
# =============================================================================

AGENT_CARD = AgentCard(
    name="FileAgent",
    description="Agent that processes file uploads and performs file transformations",
    version="1.0.0",
    url="http://localhost:8789/",
    protocol_version="0.3.0",
    provider=AgentProvider(
        organization="A2A Examples",
        url="https://github.com/a2aproject/A2A"
    ),
    capabilities=AgentCapabilities(
        streaming=False,
        push_notifications=False,
        state_transition_history=True,
    ),
    default_input_modes=["text/plain", "text/csv", "application/json"],
    default_output_modes=["text/plain", "text/csv", "application/json"],
    skills=[
        AgentSkill(
            id="analyze",
            name="analyze",
            description="Analyze a file and return statistics (size, line count, word count, etc.)",
            tags=["file", "analysis", "stats"],
            examples=["Analyze this file for me", "Get file statistics"],
            input_modes=["text/plain", "text/csv", "application/json"],
            output_modes=["application/json"],
        ),
        AgentSkill(
            id="convert_to_upper",
            name="convert_to_upper",
            description="Convert text file content to uppercase and return the transformed file",
            tags=["file", "transform", "text"],
            examples=["Convert this file to uppercase", "Make this text uppercase"],
            input_modes=["text/plain"],
            output_modes=["text/plain"],
        ),
        AgentSkill(
            id="generate_report",
            name="generate_report",
            description="Generate a sample report file in txt, csv, or json format",
            tags=["report", "generate", "file"],
            examples=["Generate a CSV report", "Create a text report"],
            input_modes=["text/plain"],
            output_modes=["text/plain", "text/csv", "application/json"],
        ),
    ],
)


# =============================================================================
# Custom Agent Executor
# =============================================================================

class FileAgentExecutor(AgentExecutor):
    """
    Custom AgentExecutor that handles file processing skills.
    
    Implements the core logic for:
    - analyze: Analyze file statistics
    - convert_to_upper: Transform text to uppercase
    - generate_report: Generate sample reports
    """

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Execute the agent's logic based on the incoming message.
        
        Args:
            context: The request context containing the message and task info
            event_queue: The queue to publish events to
        """
        message = context.message
        task_id = context.task_id
        context_id = context.context_id
        
        if not message or not task_id or not context_id:
            await self._publish_error(
                event_queue, task_id or "unknown", context_id or "unknown",
                "Missing message, task_id, or context_id"
            )
            return
        
        try:
            # Parse the message to determine what skill to execute
            skill_name, skill_params, file_part = self._parse_message(message)
            
            # Execute the appropriate skill
            if skill_name == "analyze":
                result = await self._execute_analyze(file_part)
            elif skill_name == "convert_to_upper":
                result = await self._execute_convert_to_upper(file_part)
            elif skill_name == "generate_report":
                result = await self._execute_generate_report(skill_params)
            else:
                raise FileProcessingError(f"Unknown skill: {skill_name}")
            
            # Publish the result as a completed task
            await self._publish_success(event_queue, task_id, context_id, result)
            
        except FileProcessingError as e:
            await self._publish_error(event_queue, task_id, context_id, str(e))
        except Exception as e:
            await self._publish_error(
                event_queue, task_id, context_id, f"Internal error: {str(e)}"
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Handle task cancellation requests.
        
        Args:
            context: The request context
            event_queue: The queue to publish cancellation status
        """
        from a2a.types import TaskStatusUpdateEvent
        
        task_id = context.task_id or "unknown"
        context_id = context.context_id or "unknown"
        
        cancel_event = TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.canceled,
                message=Message(
                    role=Role.agent,
                    parts=[TextPart(text="Task canceled by user")],
                    message_id=str(uuid.uuid4()),
                )
            ),
            final=True,
        )
        await event_queue.enqueue_event(cancel_event)

    def _parse_message(self, message: Message) -> tuple:
        """
        Parse the incoming message to extract skill name, params, and file.
        
        Returns:
            Tuple of (skill_name, skill_params, file_part)
        """
        skill_name = None
        skill_params = {}
        file_part = None
        
        for part in message.parts:
            if isinstance(part, TextPart):
                # Try to parse as JSON skill call
                try:
                    data = json.loads(part.text)
                    if "skill" in data:
                        skill_name = data.get("skill")
                        skill_params = data.get("params", {})
                except json.JSONDecodeError:
                    # Treat as plain text command
                    text = part.text.lower()
                    if "analyze" in text:
                        skill_name = "analyze"
                    elif "upper" in text or "uppercase" in text:
                        skill_name = "convert_to_upper"
                    elif "report" in text:
                        skill_name = "generate_report"
                        if "csv" in text:
                            skill_params = {"format": "csv"}
                        elif "json" in text:
                            skill_params = {"format": "json"}
                        else:
                            skill_params = {"format": "txt"}
            
            elif isinstance(part, FilePart):
                file_part = part
            
            elif isinstance(part, DataPart):
                # Check for skill specification in data part
                if "skill" in part.data:
                    skill_name = part.data.get("skill")
                    skill_params = part.data.get("params", {})
        
        # Default to analyze if file provided but no skill specified
        if file_part and not skill_name:
            skill_name = "analyze"
        
        if not skill_name:
            raise FileProcessingError("No skill call or file found in message")
        
        return skill_name, skill_params, file_part

    async def _execute_analyze(self, file_part: FilePart) -> Dict[str, Any]:
        """Execute the analyze skill."""
        if not file_part:
            raise FileProcessingError("No file provided for analysis")
        
        filename, mime_type, content_bytes = extract_file_from_part(file_part)
        return analyze_file(filename, mime_type, content_bytes)

    async def _execute_convert_to_upper(self, file_part: FilePart) -> Dict[str, Any]:
        """Execute the convert_to_upper skill."""
        if not file_part:
            raise FileProcessingError("No file provided for conversion")
        
        filename, mime_type, content_bytes = extract_file_from_part(file_part)
        new_name, new_content = convert_to_upper(filename, content_bytes)
        
        return {
            "file": {
                "name": new_name,
                "mime_type": mime_type or "text/plain",
                "bytes": new_content,
            },
            "message": f"Converted {filename} to uppercase"
        }

    async def _execute_generate_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the generate_report skill."""
        format_type = params.get("format", "txt")
        filename, mime_type, content_bytes = generate_report(format_type)
        
        return {
            "file": {
                "name": filename,
                "mime_type": mime_type,
                "bytes": content_bytes,
            },
            "message": f"Generated report: {filename}"
        }

    async def _publish_success(
        self, 
        event_queue: EventQueue, 
        task_id: str, 
        context_id: str, 
        result: Dict[str, Any]
    ) -> None:
        """Publish a successful task completion."""
        # Create response parts
        parts: list[Part] = []
        
        # Add text message
        if "message" in result:
            parts.append(create_text_part(result["message"]))
        
        # Add data part with analysis results
        if "file" in result:
            file_info = result["file"]
            parts.append(create_file_part(
                file_info["name"],
                file_info["mime_type"],
                file_info["bytes"]
            ))
        else:
            # Analysis results go in data part
            parts.append(create_data_part(result))
        
        # Create the completed task
        task = Task(
            id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.completed,
                message=Message(
                    role=Role.agent,
                    parts=parts,
                    message_id=str(uuid.uuid4()),
                    task_id=task_id,
                    context_id=context_id,
                )
            ),
            artifacts=[
                Artifact(
                    artifact_id=str(uuid.uuid4()),
                    parts=parts,
                    name="result" if "file" in result else "analysis",
                )
            ] if "file" in result else None,
        )
        
        await event_queue.enqueue_event(task)

    async def _publish_error(
        self, 
        event_queue: EventQueue, 
        task_id: str, 
        context_id: str, 
        error_message: str
    ) -> None:
        """Publish a task failure."""
        from a2a.types import TaskStatusUpdateEvent
        
        error_event = TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.failed,
                message=Message(
                    role=Role.agent,
                    parts=[TextPart(text=f"Error: {error_message}")],
                    message_id=str(uuid.uuid4()),
                )
            ),
            final=True,
        )
        await event_queue.enqueue_event(error_event)


# =============================================================================
# Main Application Setup
# =============================================================================

def create_app():
    """
    Create and configure the A2A FastAPI application.
    
    Returns:
        Configured FastAPI application
    """
    # Create the agent executor
    agent_executor = FileAgentExecutor()
    
    # Create the task store (in-memory for this example)
    task_store = InMemoryTaskStore()
    
    # Create the request handler
    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=task_store,
    )
    
    # Create the A2A FastAPI application
    a2a_app = A2AFastAPIApplication(
        agent_card=AGENT_CARD,
        http_handler=request_handler,
    )
    
    # Build and return the FastAPI app
    return a2a_app.build(
        title="File Agent - Google A2A SDK",
        description="File upload and processing using the official Google A2A SDK",
    )


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("File Agent - Google A2A SDK (Real Implementation)")
    print("=" * 60)
    print()
    print("Agent Card:")
    print(f"  Name: {AGENT_CARD.name}")
    print(f"  Version: {AGENT_CARD.version}")
    print(f"  URL: {AGENT_CARD.url}")
    print()
    print("Skills:")
    for skill in AGENT_CARD.skills:
        print(f"  - {skill.name}: {skill.description}")
    print()
    print("Server running at http://localhost:8789")
    print("Agent Card available at http://localhost:8789/.well-known/agent.json")
    print("=" * 60)
    
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8789)
