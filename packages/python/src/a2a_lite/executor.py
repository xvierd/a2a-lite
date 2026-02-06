"""
Wrapper around A2A's AgentExecutor that dispatches to registered skill handlers.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue

from .decorators import SkillDefinition
from .middleware import MiddlewareChain, MiddlewareContext
from .streaming import is_generator_function, stream_generator
from .utils import _is_or_subclass


class LiteAgentExecutor(AgentExecutor):
    """
    Simplified AgentExecutor with optional enterprise features.

    Features (all optional):
    - Middleware chain
    - Streaming support
    - Pydantic model conversion
    - Task context injection
    - Interaction context injection
    - Authentication
    - File part handling
    """

    def __init__(
        self,
        skills: Dict[str, SkillDefinition],
        error_handler: Optional[Callable] = None,
        middleware: Optional[MiddlewareChain] = None,
        on_complete: Optional[List[Callable]] = None,
        auth_provider: Optional[Any] = None,
        task_store: Optional[Any] = None,
    ):
        self.skills = skills
        self.error_handler = error_handler
        self.middleware = middleware or MiddlewareChain()
        self.on_complete = on_complete or []
        self.auth_provider = auth_provider
        self.task_store = task_store

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Execute a skill based on the incoming request."""
        from a2a.utils import new_agent_text_message

        try:
            # Authenticate the request (always run to produce auth_result for injection)
            auth_result = None
            if self.auth_provider:
                from .auth import AuthRequest, NoAuth
                headers = {}
                if context.call_context and context.call_context.state:
                    headers = context.call_context.state.get('headers', {})
                auth_request = AuthRequest(headers=headers)
                auth_result = await self.auth_provider.authenticate(auth_request)
                # Reject unauthenticated requests (unless NoAuth)
                if not isinstance(self.auth_provider, NoAuth) and not auth_result.authenticated:
                    error_msg = json.dumps({
                        "error": auth_result.error or "Authentication failed",
                    })
                    await event_queue.enqueue_event(new_agent_text_message(error_msg))
                    return

            # Extract message and parts
            message, parts = self._extract_message_and_parts(context)

            # Parse skill call
            skill_name, params = self._parse_message(message)

            # Build middleware context
            ctx = MiddlewareContext(
                skill=skill_name,
                params=params,
                message=message,
            )

            # Store parts and auth result in metadata for skill access
            ctx.metadata["parts"] = parts
            ctx.metadata["event_queue"] = event_queue
            ctx.metadata["auth_result"] = auth_result

            # Define final handler
            async def final_handler(ctx: MiddlewareContext) -> Any:
                return await self._execute_skill(
                    ctx.skill,
                    ctx.params,
                    event_queue,
                    ctx.metadata,
                )

            # Execute through middleware chain
            result = await self.middleware.execute(ctx, final_handler)

            # If result is not None and not already streamed, send it
            if result is not None:
                if isinstance(result, (dict, list)):
                    response_text = json.dumps(result, indent=2, default=str)
                else:
                    response_text = str(result)
                await event_queue.enqueue_event(new_agent_text_message(response_text))

            # Call completion hooks
            for hook in self.on_complete:
                try:
                    if asyncio.iscoroutinefunction(hook):
                        await hook(skill_name, result, ctx)
                    else:
                        hook(skill_name, result, ctx)
                except Exception:
                    logger.warning("Completion hook error for skill '%s'", skill_name, exc_info=True)

        except Exception as e:
            await self._handle_error(e, event_queue)

    async def _execute_skill(
        self,
        skill_name: Optional[str],
        params: Dict[str, Any],
        event_queue: EventQueue,
        metadata: Dict[str, Any],
    ) -> Any:
        """Execute a skill with the given parameters."""
        if skill_name is None:
            if not self.skills:
                return {"error": "No skills registered"}
            # Only auto-select if there's exactly one skill
            if len(self.skills) == 1:
                skill_name = list(self.skills.keys())[0]
            else:
                return {
                    "error": "No skill specified. Use {\"skill\": \"name\", \"params\": {...}} format.",
                    "available_skills": list(self.skills.keys()),
                }

        if skill_name not in self.skills:
            return {
                "error": f"Unknown skill: {skill_name}",
                "available_skills": list(self.skills.keys()),
            }

        skill_def = self.skills[skill_name]

        # Convert Pydantic models and file parts in params
        params = self._convert_params(skill_def, params, metadata)

        # Inject special contexts if needed
        if skill_def.needs_task_context and self.task_store:
            from .tasks import TaskContext, Task, TaskStatus, TaskState
            task = await self.task_store.create(skill_name, params)
            # Only pass event_queue for streaming skills (status updates go via SSE)
            eq = event_queue if skill_def.is_streaming else None
            task_ctx = TaskContext(task, eq)
            param_name = skill_def.task_context_param or "task"
            params[param_name] = task_ctx

        if skill_def.needs_auth:
            param_name = skill_def.auth_param or "auth"
            params[param_name] = metadata.get("auth_result")

        # Call the handler
        handler = skill_def.handler

        if skill_def.is_streaming or is_generator_function(handler):
            gen = handler(**params)
            await stream_generator(gen, event_queue)
            return None
        else:
            return await self._call_handler(handler, **params)

    def _convert_params(
        self,
        skill_def: SkillDefinition,
        params: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Convert parameters to Pydantic models and file parts if needed."""
        import typing
        handler = skill_def.handler
        try:
            hints = typing.get_type_hints(handler)
        except Exception:
            hints = getattr(handler, '__annotations__', {})

        from .parts import FilePart, DataPart

        converted = {}
        for param_name, value in params.items():
            if param_name == 'return':
                continue
            param_type = hints.get(param_name)

            if param_type is None:
                converted[param_name] = value
                continue

            # Skip special context types
            from .tasks import TaskContext as _TaskContext
            from .auth import AuthResult as _AuthResult
            if _is_or_subclass(param_type, _TaskContext) or _is_or_subclass(param_type, _AuthResult):
                continue

            # Convert FilePart
            if _is_or_subclass(param_type, FilePart):
                if isinstance(value, dict):
                    # Handle both A2A format and simple dict format
                    if "file" in value:
                        converted[param_name] = FilePart.from_a2a(value)
                    else:
                        # Simple format: {name, data, mime_type}
                        data = value.get("data")
                        if isinstance(data, str):
                            data = data.encode("utf-8")
                        converted[param_name] = FilePart(
                            name=value.get("name", "unknown"),
                            mime_type=value.get("mime_type", "application/octet-stream"),
                            data=data,
                            uri=value.get("uri"),
                        )
                else:
                    converted[param_name] = value
                continue

            # Convert DataPart
            if _is_or_subclass(param_type, DataPart):
                if isinstance(value, dict):
                    # Handle both A2A format and simple dict format
                    if "type" in value and value.get("type") == "data":
                        converted[param_name] = DataPart.from_a2a(value)
                    else:
                        # Simple format: pass the dict directly as data
                        converted[param_name] = DataPart(data=value)
                else:
                    converted[param_name] = value
                continue

            # Convert Pydantic models
            if hasattr(param_type, 'model_validate'):
                if isinstance(value, dict):
                    converted[param_name] = param_type.model_validate(value)
                else:
                    converted[param_name] = value
                continue

            # Default: keep as-is
            converted[param_name] = value

        return converted

    def _parse_message(self, message: str) -> tuple[Optional[str], Dict[str, Any]]:
        """Parse message to extract skill name and params."""
        try:
            data = json.loads(message)
            if isinstance(data, dict) and 'skill' in data:
                return data['skill'], data.get('params', {})
        except json.JSONDecodeError:
            logger.debug("Message is not JSON, treating as plain text")

        return None, {"message": message}

    def _extract_message_and_parts(self, context: RequestContext) -> tuple[str, List[Any]]:
        """Extract message text and any file/data parts."""
        text = ""
        parts = []

        if hasattr(context, 'message') and context.message:
            message = context.message
            if hasattr(message, 'parts'):
                raw_parts = message.parts
            else:
                raw_parts = message.get('parts', [])

            for part in raw_parts:
                if hasattr(part, 'root'):
                    part = part.root

                # Get part type
                if hasattr(part, 'text'):
                    text = part.text
                elif isinstance(part, dict):
                    part_type = part.get('type') or part.get('kind')
                    if part_type == 'text':
                        text = part.get('text', '')
                    elif part_type in ('file', 'data'):
                        parts.append(part)

        return text, parts

    async def _handle_error(self, e: Exception, event_queue: EventQueue) -> None:
        """Handle execution errors."""
        from a2a.utils import new_agent_text_message

        if self.error_handler:
            try:
                result = await self._call_handler(self.error_handler, e)
                await event_queue.enqueue_event(
                    new_agent_text_message(json.dumps(result, default=str))
                )
                return
            except Exception as handler_error:
                await event_queue.enqueue_event(
                    new_agent_text_message(json.dumps({
                        "error": str(e),
                        "handler_error": str(handler_error),
                        "type": type(e).__name__,
                    }))
                )
                return

        await event_queue.enqueue_event(
            new_agent_text_message(json.dumps({
                "error": str(e),
                "type": type(e).__name__,
            }))
        )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Handle cancellation requests."""
        from a2a.utils import new_agent_text_message
        await event_queue.enqueue_event(
            new_agent_text_message(json.dumps({"status": "cancelled"}))
        )

    async def _call_handler(self, handler: Callable, *args, **kwargs) -> Any:
        """Call a handler, handling both sync and async functions."""
        if asyncio.iscoroutinefunction(handler):
            return await handler(*args, **kwargs)
        else:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                lambda: handler(*args, **kwargs)
            )
