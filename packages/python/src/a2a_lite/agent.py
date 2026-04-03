"""
Core Agent class that wraps the A2A SDK complexity.

Simple by default, powerful when needed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)

from .decorators import SkillDefinition
from .executor import LiteAgentExecutor
from .middleware import MiddlewareChain
from .push_notifications import PushNotificationMiddleware, TaskPushRegistry
from .streaming import is_generator_function
from .utils import _is_or_subclass, extract_function_schemas

logger = logging.getLogger(__name__)


@dataclass
class Agent:
    """
    Simplified A2A Agent - simple by default, powerful when needed.

    SIMPLE (8 lines):
        agent = Agent(name="Bot", description="A bot")

        @agent.skill("greet")
        async def greet(name: str) -> str:
            return f"Hello, {name}!"

        agent.run()

    WITH PYDANTIC:
        class User(BaseModel):
            name: str

        @agent.skill("create")
        async def create(user: User) -> dict:
            return {"created": user.name}

    WITH STREAMING:
        @agent.skill("chat", streaming=True)
        async def chat(msg: str):
            for word in msg.split():
                yield word

    WITH AUTH (optional):
        from a2a_lite.auth import APIKeyAuth

        agent = Agent(
            name="SecureBot",
            auth=APIKeyAuth(keys=["secret"]),
        )

    WITH TASK TRACKING (optional):
        @agent.skill("process")
        async def process(data: str, task: TaskContext) -> str:
            await task.update("working", progress=0.5)
            return "done"

    WITH PROTOCOL TASK STORE (opt-in, for production persistence):
        from a2a_lite import Agent
        from my_stores import RedisTaskStore  # any class implementing a2a.server.tasks.TaskStore

        agent = Agent(
            name="Bot",
            description="...",
            protocol_task_store=RedisTaskStore("redis://localhost"),
        )

    WITH PUSH NOTIFICATIONS (opt-in):
        from a2a_lite import Agent, WebhookPushNotifier

        agent = Agent(
            name="Bot",
            description="...",
            push_notifier=WebhookPushNotifier(
                url="https://my-app.com/webhook",
                secret="signing-secret",
            ),
        )
    """

    name: str
    description: str
    version: str = "1.0.0"
    url: str | None = None

    # Optional enterprise features
    auth: Any | None = None  # AuthProvider
    task_store: Any | None = None  # TaskStore or "memory"
    cors_origins: list[str] | None = None
    production: bool = False
    network: Any | None = None  # AgentNetwork
    protocol_task_store: Any | None = (
        None  # SDK-level TaskStore for A2A protocol persistence (enables Redis, Postgres, etc.)
    )
    push_notifier: Any | None = None  # PushNotifier for skill completion events

    def __post_init__(self):
        # Internal state
        self._skills: dict[str, SkillDefinition] = {}
        self._error_handler: Callable | None = None
        self._on_startup: list[Callable] = []
        self._on_shutdown: list[Callable] = []
        self._on_complete: list[Callable] = []
        self._middleware = MiddlewareChain()
        self._has_streaming = False
        self._mcp_servers: list[str] = []

        # Setup optional network
        if self.network is not None:
            self._network = self.network
        else:
            self._network = None

        # Setup optional task store
        if self.task_store == "memory":
            from .tasks import TaskStore

            self._task_store = TaskStore()
        elif self.task_store:
            self._task_store = self.task_store
        else:
            self._task_store = None

        # Setup optional auth
        if self.auth is None:
            from .auth import NoAuth

            self._auth = NoAuth()
        else:
            self._auth = self.auth

        # Store push notifier
        self._push_notifier = self.push_notifier

        # Per-task push notification registry (always created)
        self.push_registry = TaskPushRegistry()

    def skill(
        self,
        name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        streaming: bool = False,
    ) -> Callable:
        """
        Decorator to register a function as an agent skill.

        Simple:
            @agent.skill("greet")
            async def greet(name: str) -> str:
                return f"Hello, {name}!"

        With streaming:
            @agent.skill("chat", streaming=True)
            async def chat(message: str):
                for word in message.split():
                    yield word

        With task context (opt-in):
            @agent.skill("process")
            async def process(data: str, task: TaskContext) -> str:
                await task.update("working", progress=0.5)
                return "done"
        """

        def decorator(func: Callable) -> Callable:
            skill_name = name or func.__name__
            skill_desc = description or func.__doc__ or f"Skill: {skill_name}"

            # Clean up docstring
            if skill_desc:
                skill_desc = " ".join(skill_desc.split())

            # Detect streaming
            is_streaming = streaming or is_generator_function(func)
            if is_streaming:
                self._has_streaming = True

            # Detect special parameter types using proper type introspection
            import typing

            from .auth import AuthResult as _AuthResult
            from .mcp import MCPClient as _MCPClient
            from .tasks import TaskContext as _TaskContext

            needs_task_context = False
            needs_auth = False
            needs_mcp = False
            task_context_param: str | None = None
            auth_param: str | None = None
            mcp_param: str | None = None

            try:
                resolved_hints = typing.get_type_hints(func)
            except Exception as e:
                logger.debug("Failed to resolve type hints for skill '%s': %s", func.__name__, e)
                resolved_hints = getattr(func, "__annotations__", {})

            for param_name, hint in resolved_hints.items():
                if param_name == "return":
                    continue
                if _is_or_subclass(hint, _TaskContext):
                    needs_task_context = True
                    task_context_param = param_name
                elif _is_or_subclass(hint, _AuthResult):
                    needs_auth = True
                    auth_param = param_name
                elif _is_or_subclass(hint, _MCPClient):
                    needs_mcp = True
                    mcp_param = param_name

            # Also detect require_auth decorator
            if getattr(func, "__requires_auth__", False) and not needs_auth:  # pragma: no cover
                needs_auth = True
                auth_param = auth_param or "auth"

            # Extract schemas
            input_schema, output_schema = extract_function_schemas(func)

            skill_def = SkillDefinition(
                name=skill_name,
                description=skill_desc,
                tags=tags or [],
                handler=func,
                input_schema=input_schema,
                output_schema=output_schema,
                is_async=asyncio.iscoroutinefunction(func) or is_streaming,
                is_streaming=is_streaming,
                needs_task_context=needs_task_context,
                needs_auth=needs_auth,
                needs_mcp=needs_mcp,
                task_context_param=task_context_param,
                auth_param=auth_param,
                mcp_param=mcp_param,
            )

            self._skills[skill_name] = skill_def
            return func

        return decorator

    def middleware(self, func: Callable) -> Callable:
        """
        Decorator to register middleware.

        Example:
            @agent.middleware
            async def log_requests(ctx, next):
                print(f"Calling: {ctx.skill}")
                return await next()
        """
        self._middleware.add(func)
        return func

    def add_middleware(self, middleware: Callable) -> None:
        """Add a middleware function (non-decorator version)."""
        self._middleware.add(middleware)

    def on_error(self, func: Callable) -> Callable:
        """Decorator to register a global error handler."""
        self._error_handler = func
        return func

    def on_startup(self, func: Callable) -> Callable:
        """Decorator to register a startup hook."""
        self._on_startup.append(func)
        return func

    def on_shutdown(self, func: Callable) -> Callable:
        """Decorator to register a shutdown hook."""
        self._on_shutdown.append(func)
        return func

    def on_complete(self, func: Callable) -> Callable:
        """Decorator to register a task completion handler."""
        self._on_complete.append(func)
        return func

    def add_mcp_server(self, url: str) -> None:
        """Register an MCP server URL for tool access in skills.

        Skills can request an MCPClient instance via type hint injection,
        which will have access to all registered MCP servers.

        Requires: pip install a2a-lite[mcp]

        Args:
            url: The MCP server URL (e.g., "http://localhost:5001").

        Example:
            agent.add_mcp_server("http://localhost:5001")

            @agent.skill("research")
            async def research(query: str, mcp: MCPClient) -> str:
                result = await mcp.call_tool("web_search", query=query)
                return result
        """
        self._mcp_servers.append(url)

    async def delegate(
        self,
        target: str,
        skill: str,
        timeout: float = 30.0,
        return_handle: bool = False,
        discover: bool = False,
        stream: bool = False,
        **params: Any,
    ) -> Any:
        """Delegate a skill call to a remote agent and return the parsed result.

        The target can be a full URL or a name registered in the agent's network.

        Args:
            target: Agent URL or network name.
            skill: The skill to invoke.
            timeout: Request timeout in seconds.
            return_handle: If True, return a TaskHandle instead of just the result.
            discover: If True, fetch the agent card first, validate the skill exists,
                      and use the card's url as the POST target.
            stream: If True, use SSE streaming and return an AsyncGenerator[str, None]
                    that yields text chunks as they arrive.
            **params: Parameters for the skill.

        Returns:
            The parsed result from the remote agent (not the raw A2A envelope),
            or a TaskHandle if return_handle=True,
            or an AsyncGenerator[str, None] if stream=True.

        Example:
            weather = await agent.delegate("http://weather:8787", "forecast", city="NYC")

            # Or with a network:
            weather = await agent.delegate("weather", "forecast", city="NYC")

            # With discovery:
            weather = await agent.delegate("weather", "forecast", discover=True, city="NYC")

            # With task handle:
            handle = await agent.delegate("weather", "forecast", return_handle=True, city="NYC")
            print(handle.task_id)

            # With streaming:
            async for chunk in agent.delegate("story", "tell", stream=True, topic="cats"):
                print(chunk, end="", flush=True)
        """
        from .orchestration import TaskHandle, _call_remote_skill, stream_remote_skill
        from .orchestration import discover as discover_agent

        # Resolve name to URL via network if available
        url = target
        if self._network is not None and not target.startswith(("http://", "https://")):
            resolved = self._network.get(target)
            if resolved is not None:
                url = resolved
            else:
                raise KeyError(f"Agent '{target}' not found in network. Available: {list(self._network.list().keys())}")

        # Optionally discover the agent card and validate the skill
        if discover:
            from .errors import SkillNotFoundError

            card = await discover_agent(url, timeout)
            # Validate the skill exists on the remote agent
            skill_names = [s.get("id") or s.get("name", "") for s in card.skills]
            if skill and skill not in skill_names:
                raise SkillNotFoundError(skill, dict.fromkeys(skill_names, ""))
            # Use the card's url as the POST target (handles non-root paths)
            url = card.url

        if stream:
            return stream_remote_skill(url, skill, params, timeout)

        result, task_id = await _call_remote_skill(url, skill, params, timeout)
        if return_handle:
            return TaskHandle(task_id=task_id, result=result, _agent_url=url)
        return result

    def build_agent_card(self, host: str = "localhost", port: int = 8787) -> AgentCard:
        """Generate A2A-compliant Agent Card from registered skills."""
        skills = []

        for skill_def in self._skills.values():
            skill = AgentSkill(
                id=skill_def.name,
                name=skill_def.name,
                description=skill_def.description,
                tags=skill_def.tags,
                inputModes=["application/json"],
                outputModes=["application/json"],
            )
            skills.append(skill)

        url = self.url or f"http://{host}:{port}"

        return AgentCard(
            name=self.name,
            description=self.description,
            version=self.version,
            url=url,
            capabilities=AgentCapabilities(
                streaming=self._has_streaming,
                pushNotifications=bool(self._on_complete) or bool(self.push_registry),
            ),
            defaultInputModes=["application/json"],
            defaultOutputModes=["application/json"],
            skills=skills,
        )

    def run(  # pragma: no cover
        self,
        host: str = "0.0.0.0",
        port: int = 8787,
        log_level: str = "info",
    ) -> None:
        """
        Start the A2A server.

        Simple:
            agent.run()

        With options:
            agent.run(port=9000)
        """
        from rich.console import Console
        from rich.panel import Panel

        console = Console()

        # Build components
        display_host = "localhost" if host == "0.0.0.0" else host

        # Build display info
        skills_list = "\n".join(
            [
                f"  • {s.name}: {s.description}" + (" [streaming]" if getattr(s, "is_streaming", False) else "")
                for s in self._skills.values()
            ]
        )
        if not skills_list:
            skills_list = "  (no skills registered)"

        # Collect enabled features
        features = []
        if len(self._middleware._middlewares):
            features.append(f"{len(self._middleware._middlewares)} middleware")
        if self._has_streaming:
            features.append("streaming")
        if self.auth:
            features.append("auth")
        if self._task_store:
            features.append("task-tracking")

        features_str = f"\n\n[bold]Features:[/] {', '.join(features)}" if features else ""

        console.print(
            Panel(
                f"[bold green]{self.name}[/] v{self.version}\n\n"
                f"[dim]{self.description}[/]\n\n"
                f"[bold]Skills:[/]\n{skills_list}{features_str}\n\n"
                f"[bold]Endpoints:[/]\n"
                f"  • Agent Card: http://{display_host}:{port}/.well-known/agent.json\n"
                f"  • API: http://{display_host}:{port}/",
                title="🚀 A2A Lite Agent Started",
                border_style="green",
            )
        )

        # Run startup hooks
        async def _run_startup():
            for hook in self._on_startup:
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()

        if self._on_startup:
            try:
                loop = asyncio.get_running_loop()
                loop.run_until_complete(_run_startup())
            except RuntimeError:
                asyncio.run(_run_startup())

        # Production mode warning
        if self.production:
            url_str = self.url or f"http://{display_host}:{port}"
            if not url_str.startswith("https://"):
                logger.warning("Running in production mode over HTTP. Consider using HTTPS for secure communication.")

        # Build the ASGI app
        app = self._build_app(display_host, port)

        # Start server
        try:
            uvicorn.run(
                app,
                host=host,
                port=port,
                log_level=log_level,
            )
        finally:
            # Run shutdown hooks
            async def _run_shutdown():
                for hook in self._on_shutdown:
                    if asyncio.iscoroutinefunction(hook):
                        await hook()
                    else:
                        hook()

            if self._on_shutdown:
                try:
                    loop = asyncio.get_running_loop()
                    loop.run_until_complete(_run_shutdown())
                except RuntimeError:
                    asyncio.run(_run_shutdown())

    async def call_remote(  # pragma: no cover
        self,
        agent_url: str,
        message: str,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Call a remote A2A agent."""
        from uuid import uuid4

        import httpx
        from a2a.client import A2AClient
        from a2a.types import MessageSendParams, SendMessageRequest

        async with httpx.AsyncClient(timeout=timeout) as http_client:
            card_url = f"{agent_url.rstrip('/')}/.well-known/agent.json"

            client = await A2AClient.get_client_from_agent_card_url(http_client, card_url)

            request = SendMessageRequest(
                id=uuid4().hex,
                params=MessageSendParams(
                    message={
                        "role": "user",
                        "parts": [{"type": "text", "text": message}],
                        "messageId": uuid4().hex,
                    }
                ),
            )

            response = await client.send_message(request)
            return response.model_dump()

    def _build_app(self, host: str = "localhost", port: int = 8787):
        """Build the Starlette ASGI application.

        Args:
            host: Hostname for the agent card URL.
            port: Port for the agent card URL.

        Returns:
            The configured Starlette application.
        """
        agent_card = self.build_agent_card(host, port)

        # Wire push notifier as first on_complete hook if configured
        on_complete = list(self._on_complete)
        if self._push_notifier is not None:
            import time as _time

            notifier = self._push_notifier
            agent_name = self.name

            async def _push_notify(skill_name: str, result: Any, ctx: Any) -> None:
                event = {
                    "skill": skill_name,
                    "result": result,
                    "status": "completed",
                    "timestamp": _time.time(),
                    "agent": agent_name,
                }
                try:
                    await notifier.notify(event)
                except Exception as e:
                    logger.warning("Push notifier error: %s", e)

            on_complete.insert(0, _push_notify)

        executor = LiteAgentExecutor(
            skills=self._skills,
            error_handler=self._error_handler,
            middleware=self._middleware,
            on_complete=on_complete,
            auth_provider=self._auth,
            task_store=self._task_store,
            mcp_servers=self._mcp_servers,
            push_registry=self.push_registry,
        )

        # SDK task store for protocol-level lifecycle (separate from app-level self._task_store)
        _protocol_store = self.protocol_task_store if self.protocol_task_store is not None else InMemoryTaskStore()
        request_handler = DefaultRequestHandler(
            agent_executor=executor,
            task_store=_protocol_store,
        )

        app_builder = A2AStarletteApplication(
            agent_card=agent_card,
            http_handler=request_handler,
        )

        app = app_builder.build()

        # Add CORS middleware if configured
        if self.cors_origins is not None:
            from starlette.middleware.cors import CORSMiddleware

            app.add_middleware(
                CORSMiddleware,
                allow_origins=self.cors_origins,
                allow_methods=["*"],
                allow_headers=["*"],
            )

        # Wrap with per-task push notification middleware (outermost layer
        # so it intercepts push-notification JSON-RPC methods before anything else)
        app = PushNotificationMiddleware(app, self.push_registry)

        return app

    def get_app(self):
        """Get the Starlette application without running it."""
        return self._build_app()

    def get_tool_schemas(self, format: str = "openai") -> list[dict]:
        """
        Return skills as tool schemas for use with LLM APIs.

        Filters out injected parameters (TaskContext, AuthResult, MCPClient)
        that are not part of the user-facing API.

        Args:
            format: Schema format. Currently only "openai" is supported.
                Returns OpenAI-compatible tool schemas.

        Returns:
            List of tool schema dicts in the requested format.

        Example (with OpenAI):
            tools = agent.get_tool_schemas()
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[...],
                tools=tools,
            )

        Example (with Anthropic):
            tools = agent.get_tool_schemas()  # same format works
            response = anthropic.messages.create(
                model="claude-sonnet-4-6",
                messages=[...],
                tools=tools,
            )
        """
        if format != "openai":
            raise ValueError(f"Unsupported schema format: {format!r}. Use 'openai'.")

        schemas = []
        for skill_def in self._skills.values():
            # Build the parameters schema, filtering out injected params
            input_schema = dict(skill_def.input_schema) if skill_def.input_schema else {}

            # Identify injected parameter names to exclude from the public schema
            injected_params = set()
            if skill_def.task_context_param:
                injected_params.add(skill_def.task_context_param)
            if skill_def.auth_param:
                injected_params.add(skill_def.auth_param)
            if skill_def.mcp_param:
                injected_params.add(skill_def.mcp_param)

            # Strip injected params from the JSON schema properties
            if injected_params and "properties" in input_schema:
                props = {k: v for k, v in input_schema["properties"].items() if k not in injected_params}
                input_schema = dict(input_schema)
                input_schema["properties"] = props
                # Also remove from required list if present
                if "required" in input_schema:
                    input_schema["required"] = [r for r in input_schema["required"] if r not in injected_params]

            # If no schema was extracted, provide a minimal one
            if not input_schema:
                input_schema = {"type": "object", "properties": {}}

            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": skill_def.name,
                        "description": skill_def.description,
                        "parameters": input_schema,
                    },
                }
            )

        return schemas
