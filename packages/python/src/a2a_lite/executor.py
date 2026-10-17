"""
Wrapper around A2A's AgentExecutor that dispatches to registered skill handlers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue

from .decorators import SkillDefinition
from .errors import (
    A2ALiteError,
    AuthRequiredError,
    ParamValidationError,
    SkillNotFoundError,
)
from .middleware import MiddlewareChain, MiddlewareContext
from .runtime import OutputLimitError
from .streaming import is_generator_function, stream_generator
from .utils import _is_or_subclass

logger = logging.getLogger(__name__)


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
        skills: dict[str, SkillDefinition],
        error_handler: Callable | None = None,
        middleware: MiddlewareChain | None = None,
        on_complete: list[Callable] | None = None,
        auth_provider: Any | None = None,
        task_store: Any | None = None,
        mcp_servers: list[str] | None = None,
        runtime_state=None,
    ):
        self.skills = skills
        self.error_handler = error_handler
        self.middleware = middleware or MiddlewareChain()
        self.on_complete = on_complete or []
        self.auth_provider = auth_provider
        self.task_store = task_store
        self.mcp_servers = mcp_servers or []
        self.runtime_state = runtime_state
        self.recovery = None

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        if self.runtime_state is not None:
            await self.runtime_state.execute(self._execute, context, event_queue)
        else:
            await self._execute(context, event_queue)

    async def _execute(self, context, event_queue):
        """Execute a skill based on the incoming request."""
        from a2a.helpers import new_text_message

        try:
            if self.recovery:
                from .recovery import EXECUTION_KEY

                text, _ = self._extract_message_and_parts(context)
                name, _ = self._parse_message(text)
                if name is None and len(self.skills) == 1:
                    name = next(iter(self.skills))
                skill = self.skills.get(name)
                if (
                    skill
                    and (skill.task_mode or skill.is_streaming)
                    and EXECUTION_KEY not in context.call_context.state
                ):
                    await self.recovery.enter(context, skill.recoverable)
            # Authenticate the request (always run to produce auth_result for injection)
            auth_result = context.call_context.state.get("auth_result") if context.call_context else None
            if self.auth_provider:
                from .auth import AuthRequest, NoAuth

                headers = {}
                if context.call_context and context.call_context.state:
                    headers = context.call_context.state.get("headers", {})
                auth_request = AuthRequest(headers=headers)
                if auth_result is None:
                    auth_result = await self.auth_provider.authenticate(auth_request)
                # Reject unauthenticated requests (unless NoAuth)
                if not isinstance(self.auth_provider, NoAuth) and not auth_result.authenticated:
                    scheme = self.auth_provider.get_scheme() if hasattr(self.auth_provider, "get_scheme") else {}
                    scheme_type = scheme.get("type", "unknown")
                    scheme_name = scheme.get("name", "")
                    if scheme_type == "apiKey":
                        detail = f"Pass your key via the '{scheme_name or 'X-API-Key'}' header."
                        scheme_info = "API Key auth"
                    elif scheme_type == "http" and scheme.get("scheme") == "bearer":
                        detail = "Pass your token via the 'Authorization: Bearer <token>' header."
                        scheme_info = "Bearer token auth"
                    elif scheme_type == "oauth2":
                        detail = "Obtain a token from the OAuth2 provider."
                        scheme_info = "OAuth2 auth"
                    else:
                        detail = auth_result.error or None
                        scheme_info = "authentication"
                    auth_err = AuthRequiredError(scheme_info=scheme_info, detail=detail)
                    error_msg = json.dumps(auth_err.to_response())
                    await event_queue.enqueue_event(new_text_message(error_msg))
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
            ctx.metadata["request_context"] = context

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
                await event_queue.enqueue_event(new_text_message(response_text))

            # Call completion hooks
            for hook in self.on_complete:
                try:
                    if asyncio.iscoroutinefunction(hook):
                        await hook(skill_name, result, ctx)
                    else:
                        hook(skill_name, result, ctx)
                except Exception:
                    logger.warning(
                        "Completion hook error for skill '%s'",
                        skill_name,
                        exc_info=True,
                    )

        except OutputLimitError:
            raise
        except Exception as e:
            await self._handle_error(e, event_queue)

    async def _execute_skill(
        self,
        skill_name: str | None,
        params: dict[str, Any],
        event_queue: EventQueue,
        metadata: dict[str, Any],
    ) -> Any:
        """Execute a skill with the given parameters."""
        available = {name: sd.description for name, sd in self.skills.items()}

        if skill_name is None:
            if not self.skills:
                return {"error": "No skills registered"}
            # Only auto-select if there's exactly one skill
            if len(self.skills) == 1:
                skill_name = list(self.skills.keys())[0]
            else:
                err = SkillNotFoundError(
                    skill="(none)",
                    available_skills=available,
                )
                return err.to_response()

        if skill_name not in self.skills:
            err = SkillNotFoundError(
                skill=skill_name,
                available_skills=available,
            )
            return err.to_response()

        skill_def = self.skills[skill_name]

        # Convert Pydantic models and file parts in params — catch validation errors
        try:
            params = self._convert_params(skill_def, params, metadata)
        except Exception as conv_err:
            # Check for Pydantic ValidationError
            if type(conv_err).__name__ == "ValidationError" and hasattr(conv_err, "errors"):
                errors = []
                for e in conv_err.errors():  # type: ignore[union-attr]
                    field = ".".join(str(loc) for loc in e.get("loc", []))
                    errors.append(
                        {
                            "field": field,
                            "message": e.get("msg", str(e)),
                            "type": e.get("type", "unknown"),
                        }
                    )
                param_err = ParamValidationError(skill=skill_name, errors=errors)
                return param_err.to_response()
            raise

        # Call the handler
        handler = skill_def.handler
        is_streaming_skill = skill_def.is_streaming or is_generator_function(handler)

        # Task mode is explicit or inferred from TaskContext/streaming. The
        # protocol-assigned identity is the only task ID exposed to a skill.
        updater = None
        task_ctx = None
        if is_streaming_skill or skill_def.task_mode or skill_def.needs_task_context:
            request_context = metadata.get("request_context")
            if request_context is not None:
                from a2a.helpers import new_task_from_user_message
                from a2a.server.tasks import TaskUpdater

                protocol_task = request_context.current_task or new_task_from_user_message(request_context.message)
                protocol_task.id = request_context.task_id
                protocol_task.context_id = request_context.context_id
                if request_context.current_task is not None:
                    from a2a.types import TaskState as A2ATaskState

                    protocol_task.status.state = A2ATaskState.TASK_STATE_WORKING
                await event_queue.enqueue_event(protocol_task)
                updater = TaskUpdater(event_queue, protocol_task.id, protocol_task.context_id)
                await updater.start_work()
                metadata["task_updater"] = updater

        # Inject special contexts if needed
        if skill_def.needs_task_context:
            from .tasks import Task, TaskContext, TaskState, TaskStatus

            if updater is not None:
                local_task = Task(
                    id=updater.task_id, skill=skill_name, params=dict(params), status=TaskStatus(TaskState.WORKING)
                )
                if self.task_store:
                    await self.task_store.update(local_task)
            elif self.task_store:
                local_task = await self.task_store.create(skill_name, params)
            else:
                raise RuntimeError("TaskContext requires a protocol request context")
            task_ctx = TaskContext(local_task, updater)
            if request_context is not None and request_context.call_context:
                task_ctx._execution = request_context.call_context.state.get("a2a_lite.execution")
            param_name = skill_def.task_context_param or "task"
            params[param_name] = task_ctx

        if skill_def.needs_auth:
            param_name = skill_def.auth_param or "auth"
            params[param_name] = metadata.get("auth_result")

        if skill_def.needs_mcp and self.mcp_servers:
            from .mcp import MCPClient

            mcp_client = MCPClient(server_urls=self.mcp_servers)
            param_name = skill_def.mcp_param or "mcp"
            params[param_name] = mcp_client

        try:
            if is_streaming_skill:
                gen = handler(**params)
                await stream_generator(gen, event_queue, updater=updater)
                return None
            result = await self._call_handler(handler, **params)
            if updater is None:
                return result
            from a2a.helpers import new_text_part

            if task_ctx is None or task_ctx.state not in (
                TaskState.COMPLETED,
                TaskState.FAILED,
                TaskState.CANCELED,
                TaskState.INPUT_REQUIRED,
                TaskState.AUTH_REQUIRED,
            ):
                text = json.dumps(result, default=str) if not isinstance(result, str) else result
                await updater.add_artifact([new_text_part(text)], name="result")
                await updater.complete()
                if task_ctx is not None:
                    task_ctx._task.result = result
                    task_ctx._task.update_status(TaskState.COMPLETED)
                    if self.task_store:
                        await self.task_store.update(task_ctx._task)
            return None
        except OutputLimitError:
            raise
        except Exception as error:
            if updater is None:
                raise
            from a2a.helpers import new_text_part

            if task_ctx is not None and task_ctx.state in (
                TaskState.COMPLETED,
                TaskState.FAILED,
                TaskState.CANCELED,
                TaskState.INPUT_REQUIRED,
                TaskState.AUTH_REQUIRED,
            ):
                return None
            detail = (
                str(error)
                if self.runtime_state is None or self.runtime_state.config.profile == "learning"
                else "Skill execution failed"
            )
            await updater.failed(updater.new_agent_message([new_text_part(json.dumps({"error": detail}))]))
            if task_ctx is not None:
                task_ctx._task.error = str(error)
                task_ctx._task.update_status(TaskState.FAILED)
                if self.task_store:
                    await self.task_store.update(task_ctx._task)
            return None

    def _convert_params(
        self,
        skill_def: SkillDefinition,
        params: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert parameters to Pydantic models and file parts if needed."""
        import typing

        handler = skill_def.handler
        try:
            hints = typing.get_type_hints(handler)
        except Exception as e:
            logger.debug("Failed to get type hints for handler '%s': %s", getattr(handler, "__name__", "unknown"), e)
            hints = getattr(handler, "__annotations__", {})

        from .parts import DataPart, FilePart

        converted = {}
        for param_name, value in params.items():
            if param_name == "return":
                continue
            param_type = hints.get(param_name)

            if param_type is None:
                converted[param_name] = value
                continue

            # Skip special context types
            from .auth import AuthResult as _AuthResult
            from .mcp import MCPClient as _MCPClient
            from .tasks import TaskContext as _TaskContext

            if (
                _is_or_subclass(param_type, _TaskContext)
                or _is_or_subclass(param_type, _AuthResult)
                or _is_or_subclass(param_type, _MCPClient)
            ):
                continue

            # Convert FilePart
            if _is_or_subclass(param_type, FilePart):
                if isinstance(value, dict):
                    # Handle both A2A v1.0 format and simple dict format
                    if "raw" in value or "url" in value:
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
                    # Handle both A2A v1.0 format and simple dict format
                    if (
                        "data" in value
                        and isinstance(value.get("data"), dict)
                        and set(value.keys())
                        <= {
                            "data",
                            "mediaType",
                            "metadata",
                        }
                    ):
                        converted[param_name] = DataPart.from_a2a(value)
                    else:
                        # Simple format: pass the dict directly as data
                        converted[param_name] = DataPart(data=value)
                else:
                    converted[param_name] = value
                continue

            # Convert Pydantic models
            if hasattr(param_type, "model_validate"):
                if isinstance(value, dict):
                    converted[param_name] = param_type.model_validate(value)
                else:
                    converted[param_name] = value
                continue

            # Default: keep as-is
            converted[param_name] = value

        return converted

    def _parse_message(self, message: str) -> tuple[str | None, dict[str, Any]]:
        """Parse message to extract skill name and params."""
        try:
            data = json.loads(message)
            if isinstance(data, dict) and "skill" in data:
                return data["skill"], data.get("params", {})
        except json.JSONDecodeError:
            logger.debug("Message is not JSON, treating as plain text")

        return None, {"message": message}

    def _extract_message_and_parts(self, context: RequestContext) -> tuple[str, list[Any]]:
        """Extract message text and any file/data parts.

        A2A 1.x: Message is a protobuf message. Text is read via the SDK
        helper; file/data parts are detected by oneof presence (raw/url/data)
        and converted to plain dicts for skill access.
        """
        text = ""
        parts = []

        if hasattr(context, "message") and context.message:
            message = context.message
            if hasattr(message, "parts"):
                from a2a.helpers import get_message_text

                text = get_message_text(message)

                from google.protobuf.json_format import MessageToDict

                for part in message.parts:
                    if part.HasField("text"):
                        continue
                    if part.HasField("raw") or part.HasField("url") or part.HasField("data"):
                        parts.append(MessageToDict(part))

        return text, parts

    async def _handle_error(self, e: Exception, event_queue: EventQueue) -> None:
        """Handle execution errors."""
        from a2a.helpers import new_text_message

        if (
            self.runtime_state is not None
            and self.runtime_state.config.profile != "learning"
            and not isinstance(e, A2ALiteError)
            and self.error_handler is None
        ):
            await event_queue.enqueue_event(new_text_message(json.dumps({"error": "Skill execution failed"})))
            return
        if self.error_handler:
            try:
                result = await self._call_handler(self.error_handler, e)
                await event_queue.enqueue_event(new_text_message(json.dumps(result, default=str)))
                return
            except Exception as handler_error:
                await event_queue.enqueue_event(
                    new_text_message(
                        json.dumps(
                            {
                                "error": str(e),
                                "handler_error": str(handler_error),
                                "type": type(e).__name__,
                            }
                        )
                    )
                )
                return

        # Use structured response for A2ALiteError subtypes
        if isinstance(e, A2ALiteError):
            await event_queue.enqueue_event(new_text_message(json.dumps(e.to_response())))
            return

        await event_queue.enqueue_event(
            new_text_message(
                json.dumps(
                    {
                        "error": str(e),
                        "type": type(e).__name__,
                    }
                )
            )
        )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Handle cancellation requests."""
        from a2a.server.tasks import TaskUpdater

        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()

    async def _call_handler(self, handler: Callable, *args, **kwargs) -> Any:
        """Call a handler, handling both sync and async functions."""
        if asyncio.iscoroutinefunction(handler):
            return await handler(*args, **kwargs)
        else:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: handler(*args, **kwargs))
