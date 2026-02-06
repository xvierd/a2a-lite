"""
Core Agent class that wraps the A2A SDK complexity.

Simple by default, powerful when needed.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Callable, Optional, Dict, List, Type, Union, get_origin, get_args
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCard,
    AgentSkill,
    AgentCapabilities,
)

from .executor import LiteAgentExecutor
from .decorators import SkillDefinition
from .utils import type_to_json_schema, extract_function_schemas, _is_or_subclass
from .middleware import MiddlewareChain, MiddlewareContext
from .streaming import is_generator_function


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
    """
    name: str
    description: str
    version: str = "1.0.0"
    url: Optional[str] = None

    # Optional enterprise features
    auth: Optional[Any] = None  # AuthProvider
    task_store: Optional[Any] = None  # TaskStore or "memory"
    cors_origins: Optional[List[str]] = None
    production: bool = False

    def __post_init__(self):
        # Internal state
        self._skills: Dict[str, SkillDefinition] = {}
        self._error_handler: Optional[Callable] = None
        self._on_startup: List[Callable] = []
        self._on_shutdown: List[Callable] = []
        self._on_complete: List[Callable] = []
        self._middleware = MiddlewareChain()
        self._has_streaming = False

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

    def skill(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
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
            from .tasks import TaskContext as _TaskContext
            from .auth import AuthResult as _AuthResult

            needs_task_context = False
            needs_auth = False
            task_context_param: str | None = None
            auth_param: str | None = None

            try:
                resolved_hints = typing.get_type_hints(func)
            except Exception:
                resolved_hints = getattr(func, '__annotations__', {})

            for param_name, hint in resolved_hints.items():
                if param_name == 'return':
                    continue
                if _is_or_subclass(hint, _TaskContext):
                    needs_task_context = True
                    task_context_param = param_name
                elif _is_or_subclass(hint, _AuthResult):
                    needs_auth = True
                    auth_param = param_name

            # Also detect require_auth decorator
            if getattr(func, '__requires_auth__', False) and not needs_auth:
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
                task_context_param=task_context_param,
                auth_param=auth_param,
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
                pushNotifications=bool(self._on_complete),
            ),
            defaultInputModes=["application/json"],
            defaultOutputModes=["application/json"],
            skills=skills,
        )

    def run(
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
        agent_card = self.build_agent_card(display_host, port)
        executor = LiteAgentExecutor(
            skills=self._skills,
            error_handler=self._error_handler,
            middleware=self._middleware,
            on_complete=self._on_complete,
            auth_provider=self._auth,
            task_store=self._task_store,
        )

        # The SDK's InMemoryTaskStore handles protocol-level task lifecycle
        # (task creation, state transitions per the A2A spec). This is separate
        # from self._task_store which provides application-level tracking
        # (progress updates, custom status) exposed via TaskContext to skills.
        request_handler = DefaultRequestHandler(
            agent_executor=executor,
            task_store=InMemoryTaskStore(),
        )

        app_builder = A2AStarletteApplication(
            agent_card=agent_card,
            http_handler=request_handler,
        )

        # Build display info
        skills_list = "\n".join([
            f"  • {s.name}: {s.description}" +
            (" [streaming]" if getattr(s, 'is_streaming', False) else "")
            for s in self._skills.values()
        ])
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

        console.print(Panel(
            f"[bold green]{self.name}[/] v{self.version}\n\n"
            f"[dim]{self.description}[/]\n\n"
            f"[bold]Skills:[/]\n{skills_list}{features_str}\n\n"
            f"[bold]Endpoints:[/]\n"
            f"  • Agent Card: http://{display_host}:{port}/.well-known/agent.json\n"
            f"  • API: http://{display_host}:{port}/",
            title="🚀 A2A Lite Agent Started",
            border_style="green",
        ))

        # Run startup hooks
        async def _run_startup():
            for hook in self._on_startup:
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()
        if self._on_startup:
            asyncio.run(_run_startup())

        # Production mode warning
        if self.production:
            url_str = self.url or f"http://{display_host}:{port}"
            if not url_str.startswith("https://"):
                logger.warning(
                    "Running in production mode over HTTP. "
                    "Consider using HTTPS for secure communication."
                )

        # Build the ASGI app
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
                asyncio.run(_run_shutdown())

    async def call_remote(
        self,
        agent_url: str,
        message: str,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """Call a remote A2A agent."""
        import httpx
        from a2a.client import A2AClient
        from a2a.types import MessageSendParams, SendMessageRequest
        from uuid import uuid4

        async with httpx.AsyncClient(timeout=timeout) as http_client:
            card_url = f"{agent_url.rstrip('/')}/.well-known/agent.json"

            client = await A2AClient.get_client_from_agent_card_url(
                http_client, card_url
            )

            request = SendMessageRequest(
                id=uuid4().hex,
                params=MessageSendParams(
                    message={
                        "role": "user",
                        "parts": [{"type": "text", "text": message}],
                        "messageId": uuid4().hex,
                    }
                )
            )

            response = await client.send_message(request)
            return response.model_dump()

    def get_app(self):
        """Get the Starlette application without running it."""
        agent_card = self.build_agent_card()
        executor = LiteAgentExecutor(
            skills=self._skills,
            error_handler=self._error_handler,
            middleware=self._middleware,
            on_complete=self._on_complete,
            auth_provider=self._auth,
            task_store=self._task_store,
        )

        # SDK task store for protocol-level lifecycle (separate from app-level self._task_store)
        request_handler = DefaultRequestHandler(
            agent_executor=executor,
            task_store=InMemoryTaskStore(),
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

        return app
