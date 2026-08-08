#!/usr/bin/env python3
"""
File Handling Agent - Google A2A SDK Implementation (A2A v1.0)

Demonstrates file upload/download handling using the official a2a-sdk 1.x.

v1.0 changes vs 0.3:
- FilePart/FileWithBytes/DataPart are gone. A single `Part` type carries
  text / raw (bytes) / url / data + filename/media_type metadata.
- The server is assembled from route factories on a plain Starlette app.
- The executor follows the task pattern: Task first, then TaskUpdater
  (artifacts + complete/failed).

Usage:
    pip install -r requirements.txt
    python main.py

The server will start on http://localhost:8789
"""

import json
import os
from typing import Any, Dict, Optional

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
    AgentProvider,
    AgentSkill,
    Message,
    Part,
)

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

AGENT_URL = "http://localhost:8789/"


# =============================================================================
# Agent Card Configuration
# =============================================================================

AGENT_CARD = AgentCard(
    name="FileAgent",
    description="Agent that processes file uploads and performs file transformations",
    version="1.0.0",
    supported_interfaces=[
        AgentInterface(
            url=AGENT_URL,
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        ),
    ],
    provider=AgentProvider(
        organization="A2A Examples",
        url="https://github.com/a2aproject/A2A"
    ),
    capabilities=AgentCapabilities(
        streaming=False,
        push_notifications=False,
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

        v1.0 task pattern: enqueue the Task first, then drive everything
        through TaskUpdater.
        """
        task = context.current_task or new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        message = context.message
        if not message:
            await updater.failed(
                message=updater.new_agent_message([create_text_part("No message in request")])
            )
            return

        try:
            # Parse the message to determine what skill to execute
            skill_name, skill_params, file_part = self._parse_message(message)

            # Execute the appropriate skill
            if skill_name == "analyze":
                result = self._execute_analyze(file_part)
            elif skill_name == "convert_to_upper":
                result = self._execute_convert_to_upper(file_part)
            elif skill_name == "generate_report":
                result = self._execute_generate_report(skill_params)
            else:
                raise FileProcessingError(f"Unknown skill: {skill_name}")

            await self._publish_success(updater, result)

        except FileProcessingError as e:
            await updater.failed(
                message=updater.new_agent_message([create_text_part(f"Error: {e}")])
            )
        except Exception as e:
            await updater.failed(
                message=updater.new_agent_message([create_text_part(f"Internal error: {e}")])
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Handle task cancellation requests."""
        task = context.current_task
        if task is not None:
            updater = TaskUpdater(event_queue, task.id, task.context_id)
            await updater.cancel()

    def _parse_message(self, message: Message) -> tuple:
        """
        Parse the incoming message to extract skill name, params, and file.

        v1.0: inspect the Part oneof with HasField().

        Returns:
            Tuple of (skill_name, skill_params, file_part)
        """
        skill_name = None
        skill_params: Dict[str, Any] = {}
        file_part: Optional[Part] = None

        for part in message.parts:
            if part.HasField("text"):
                # Try to parse as JSON skill call
                try:
                    data = json.loads(part.text)
                    if "skill" in data:
                        skill_name = data.get("skill")
                        skill_params = data.get("params", {})
                        continue
                except json.JSONDecodeError:
                    pass
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

            elif part.HasField("raw") or part.HasField("url"):
                file_part = part

            elif part.HasField("data"):
                data = dict(part.data)
                if "skill" in data:
                    skill_name = data.get("skill")
                    skill_params = data.get("params", {})

        # Default to analyze if file provided but no skill specified
        if file_part and not skill_name:
            skill_name = "analyze"

        if not skill_name:
            raise FileProcessingError("No skill call or file found in message")

        return skill_name, skill_params, file_part

    def _execute_analyze(self, file_part: Optional[Part]) -> Dict[str, Any]:
        """Execute the analyze skill."""
        if not file_part:
            raise FileProcessingError("No file provided for analysis")

        filename, mime_type, content_bytes = extract_file_from_part(file_part)
        return analyze_file(filename, mime_type, content_bytes)

    def _execute_convert_to_upper(self, file_part: Optional[Part]) -> Dict[str, Any]:
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

    def _execute_generate_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
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
        updater: TaskUpdater,
        result: Dict[str, Any]
    ) -> None:
        """Publish a successful task completion with artifacts."""
        if "file" in result:
            # Return the produced file as a raw-bytes artifact
            file_info = result["file"]
            await updater.add_artifact(
                [create_file_part(
                    file_info["name"],
                    file_info["mime_type"],
                    file_info["bytes"],
                )],
                name="result",
            )
        else:
            # Analysis results go in a structured-data artifact
            await updater.add_artifact(
                [create_data_part(result)],
                name="analysis",
            )

        summary = result.get("message", "Done")
        await updater.complete(
            message=updater.new_agent_message([create_text_part(summary)])
        )


# =============================================================================
# Main Application Setup
# =============================================================================

def create_app() -> Starlette:
    """Create and configure the A2A Starlette application."""
    agent_executor = FileAgentExecutor()
    task_store = InMemoryTaskStore()

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


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("File Agent - Google A2A SDK (Real Implementation) - A2A v1.0")
    print("=" * 60)
    print()
    print("Agent Card:")
    print(f"  Name: {AGENT_CARD.name}")
    print(f"  Version: {AGENT_CARD.version}")
    print()
    print("Skills:")
    for skill in AGENT_CARD.skills:
        print(f"  - {skill.name}: {skill.description}")
    print()
    print("Server running at http://localhost:8789")
    print("Agent Card available at http://localhost:8789/.well-known/agent-card.json")
    print("=" * 60)

    app = create_app()
    port = int(os.getenv("PORT", "8789"))
    uvicorn.run(app, host="0.0.0.0", port=port)
