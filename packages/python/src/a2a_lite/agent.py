"""
Core Agent class that wraps the A2A SDK complexity.

Simple by default, powerful when needed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes, create_rest_routes
from a2a.server.tasks import InMemoryPushNotificationConfigStore, InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
)

from .client import ClientConfig
from .decorators import SkillDefinition
from .executor import LiteAgentExecutor
from .middleware import MiddlewareChain
from .push_notifications import ProtocolPushSender, create_push_http_client, validate_callback_url
from .server import AuthenticatedContextBuilder, LiteRequestHandler, ProtocolMiddleware
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

    WITH GRPC (EXPERIMENTAL, opt-in):
        # Requires: pip install a2a-lite[grpc]
        agent.run_grpc()  # serves gRPC on 0.0.0.0:50051 (standalone, no HTTP app)
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
    runtime: Any | None = None  # RuntimeConfig
    persistence: Any | None = None  # PersistenceConfig

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

        from .auth import NoAuth
        from .runtime import RuntimeConfig

        self._runtime_config = self.runtime or RuntimeConfig()
        if self._runtime_config.profile != "learning" and isinstance(self._auth, NoAuth):
            raise ValueError("Authenticated and durable profiles require an auth provider")
        if self._runtime_config.profile == "durable" and self.persistence is None:
            raise ValueError("Durable profile requires PersistenceConfig")
        if self.persistence is not None and self.protocol_task_store is not None:
            raise ValueError("Choose persistence or protocol_task_store, not both")

        # Store push notifier
        self._push_notifier = self.push_notifier

        # Per-task push notification registry (always created)
        self.push_registry = InMemoryPushNotificationConfigStore()

    def skill(
        self,
        name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        streaming: bool = False,
        task: bool = False,
        recoverable: bool = False,
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

            if recoverable and self.persistence is None:
                raise ValueError("Recoverable skills require PersistenceConfig")
            if recoverable and (streaming or is_generator_function(func)):
                raise ValueError("Recoverable skills currently return a single result; streaming is unsupported")

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
            if task or needs_task_context or recoverable:
                self._has_streaming = True

            skill_def = SkillDefinition(
                name=skill_name,
                description=skill_desc,
                tags=tags or [],
                handler=func,
                input_schema=input_schema,
                output_schema=output_schema,
                is_async=asyncio.iscoroutinefunction(func) or is_streaming,
                is_streaming=is_streaming,
                task_mode=task or needs_task_context or recoverable,
                recoverable=recoverable,
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
        /,
        timeout: float = 30.0,
        return_handle: bool = False,
        discover: bool = False,
        stream: bool = False,
        client_config: ClientConfig | None = None,
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
                client_config = client_config or self._network._clients.get(target)
            else:
                raise KeyError(f"Agent '{target}' not found in network. Available: {list(self._network.list().keys())}")

        client_config = (client_config or ClientConfig()).bind(url)
        # Optionally discover the agent card and validate the skill
        if discover:
            from .errors import SkillNotFoundError

            discovery_url = self._network._discovery_urls.get(target, url) if self._network else url
            card = await discover_agent(discovery_url, timeout, client_config=client_config)
            # Validate the skill exists on the remote agent
            skill_names = [s.get("id") or s.get("name", "") for s in card.skills]
            if skill and skill not in skill_names:
                raise SkillNotFoundError(skill, dict.fromkeys(skill_names, ""))
            # Use the card's url as the POST target (handles non-root paths)
            url = card.url

        if stream:
            return stream_remote_skill(url, skill, params, timeout, client_config=client_config)

        result, task_id = await _call_remote_skill(url, skill, params, timeout, client_config=client_config)
        if return_handle:
            return TaskHandle(task_id=task_id, result=result, _agent_url=url, _client=client_config)
        return result

    def build_agent_card(self, host: str = "localhost", port: int = 8787, grpc_url: str | None = None) -> AgentCard:
        """Generate A2A 1.0-compliant Agent Card from registered skills.

        Args:
            host: Hostname for the HTTP interface URLs.
            port: Port for the HTTP interface URLs.
            grpc_url: Optional "host:port" of a running gRPC endpoint (EXPERIMENTAL).
                When provided, a GRPC AgentInterface is added to supported_interfaces.
        """
        skills = []

        for skill_def in self._skills.values():
            skill = AgentSkill(
                id=skill_def.name,
                name=skill_def.name,
                description=skill_def.description,
                tags=skill_def.tags,
                input_modes=["application/json"],
                output_modes=["application/json"],
            )
            skills.append(skill)

        url = self.url or f"http://{host}:{port}"

        supported_interfaces = [
            AgentInterface(url=url, protocol_binding="JSONRPC", protocol_version="1.0"),
            AgentInterface(url=url, protocol_binding="HTTP+JSON", protocol_version="1.0"),
        ]
        if grpc_url is not None:
            supported_interfaces.append(AgentInterface(url=grpc_url, protocol_binding="GRPC", protocol_version="1.0"))

        card_kwargs: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "supported_interfaces": supported_interfaces,
            "capabilities": AgentCapabilities(
                streaming=self._has_streaming,
                push_notifications=bool(self._on_complete) or bool(self.push_registry),
            ),
            "default_input_modes": ["application/json"],
            "default_output_modes": ["application/json"],
            "skills": skills,
        }

        # Advertise the security scheme when an auth provider is configured
        security_schemes, security_requirements = self._build_security_schemes()
        if security_schemes:
            card_kwargs["security_schemes"] = security_schemes
            card_kwargs["security_requirements"] = security_requirements

        return AgentCard(**card_kwargs)

    def _build_security_schemes(self) -> tuple[dict, list]:
        """Convert the auth provider's scheme dict to A2A 1.0 proto types.

        Returns (security_schemes_map, security_requirements) or ({}, [])
        when no auth provider is configured.
        """
        if self.auth is None or not hasattr(self._auth, "get_scheme"):
            return {}, []

        scheme = self._auth.get_scheme()
        if not scheme:
            return {}, []

        from a2a.types import (
            APIKeySecurityScheme,
            AuthorizationCodeOAuthFlow,
            HTTPAuthSecurityScheme,
            OAuth2SecurityScheme,
            OAuthFlows,
            SecurityRequirement,
            SecurityScheme,
        )

        scheme_type = scheme.get("type")

        if scheme_type == "apiKey":
            name = "apiKey"
            proto_scheme = SecurityScheme(
                api_key_security_scheme=APIKeySecurityScheme(
                    name=scheme.get("name", "X-API-Key"),
                    location=scheme.get("in", "header"),
                )
            )
        elif scheme_type == "http":
            name = scheme.get("scheme", "http")
            proto_scheme = SecurityScheme(
                http_auth_security_scheme=HTTPAuthSecurityScheme(
                    scheme=scheme.get("scheme", "bearer"),
                )
            )
        elif scheme_type == "oauth2":
            name = "oauth2"
            flows_dict = scheme.get("flows", {})
            auth_code = flows_dict.get("authorizationCode", {})
            proto_scheme = SecurityScheme(
                oauth2_security_scheme=OAuth2SecurityScheme(
                    flows=OAuthFlows(
                        authorization_code=AuthorizationCodeOAuthFlow(
                            authorization_url=auth_code.get("authorizationUrl", ""),
                            token_url=auth_code.get("tokenUrl", ""),
                            scopes=auth_code.get("scopes", {}),
                        )
                    )
                )
            )
        else:
            logger.warning("Unknown auth scheme type %r; skipping agent card security schemes", scheme_type)
            return {}, []

        requirement = SecurityRequirement()
        requirement.schemes[name]  # empty scope list
        return {name: proto_scheme}, [requirement]

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
                f"  • Agent Card: http://{display_host}:{port}/.well-known/agent-card.json\n"
                f"  • API: http://{display_host}:{port}/",
                title="🚀 A2A Lite Agent Started",
                border_style="green",
            )
        )

        if self.production and not (self.url or "").startswith("https://"):
            logger.warning("Running in production mode over HTTP. Consider HTTPS for secure communication.")
        uvicorn.run(
            self._build_app(display_host, port),
            host=host,
            port=port,
            log_level=log_level,
            timeout_graceful_shutdown=self._runtime_config.shutdown_timeout,
        )

    async def start(self, host: str = "127.0.0.1", port: int = 0, log_level: str = "warning"):
        """Start HTTP in this event loop and return a ManagedRuntime."""
        from .runtime import start_http

        return await start_http(self, host, port, log_level)

    async def call_remote(  # pragma: no cover
        self,
        agent_url: str,
        message: str,
        timeout: float = 30.0,
        *,
        client_config: ClientConfig | None = None,
    ) -> dict[str, Any]:
        """Call a remote A2A agent (JSON-RPC SendMessage, wire v1.0)."""
        from uuid import uuid4

        import httpx

        request_body = {
            "jsonrpc": "2.0",
            "method": "SendMessage",
            "id": uuid4().hex,
            "params": {
                "message": {
                    "role": "ROLE_USER",
                    "parts": [{"text": message}],
                    "messageId": uuid4().hex,
                }
            },
        }

        config = (client_config or ClientConfig()).bind(agent_url)
        request_body["params"] = config.request_params(request_body["params"])
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as http_client:
            response = await http_client.post(
                agent_url,
                json=request_body,
                headers=await config.request_headers(agent_url),
            )
            response.raise_for_status()
            return response.json()

    def _build_request_handler(self, agent_card: AgentCard) -> DefaultRequestHandler:
        """Build the SDK DefaultRequestHandler (shared executor + task store wiring)."""
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

        from .runtime import RuntimeLifecycle, RuntimeState

        state = RuntimeState(self._runtime_config)
        executor = LiteAgentExecutor(
            skills=self._skills,
            error_handler=self._error_handler,
            middleware=self._middleware,
            on_complete=on_complete,
            auth_provider=self._auth,
            task_store=self._task_store,
            mcp_servers=self._mcp_servers,
            runtime_state=state,
        )

        # SDK task store for protocol-level lifecycle (separate from app-level self._task_store)
        _protocol_store = self.protocol_task_store if self.protocol_task_store is not None else InMemoryTaskStore()
        backend = self.persistence.build() if self.persistence is not None else None
        if backend is not None:
            backend.recovery.executor = executor
            executor.recovery = backend.recovery
            _protocol_store = backend.task_store
            self.push_registry = backend.push_store
        from .stores import bound_task_store

        _protocol_store = bound_task_store(_protocol_store, self._runtime_config)
        if backend is not None:
            backend.task_store = _protocol_store
        push_http_client = create_push_http_client()
        handler = LiteRequestHandler(
            agent_executor=executor,
            task_store=_protocol_store,
            agent_card=agent_card,
            push_http_client=push_http_client,
            push_config_store=self.push_registry,
            push_sender=backend.push_sender
            if backend is not None
            else ProtocolPushSender(push_http_client, self.push_registry, push_url_validator=validate_callback_url),
            event_stream=backend.event_stream if backend is not None else None,
            push_url_validator=validate_callback_url,
        )
        handler.runtime = RuntimeLifecycle(self, handler, state, backend)
        return handler

    def _build_app(self, host: str = "localhost", port: int = 8787):
        """Build the Starlette ASGI application.

        Args:
            host: Hostname for the agent card URL.
            port: Port for the agent card URL.

        Returns:
            The configured Starlette application.
        """
        agent_card = self.build_agent_card(host, port)
        request_handler = self._build_request_handler(agent_card)

        from starlette.applications import Starlette

        @asynccontextmanager
        async def lifespan(app):
            await request_handler.runtime.start()
            try:
                yield
            finally:
                await request_handler.runtime.stop()

        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def live(request):
            return JSONResponse({"live": True})

        async def ready(request):
            lifecycle = request_handler.runtime
            available = lifecycle.state.ready and lifecycle.state.accepting
            if available and lifecycle.backend:
                try:
                    await asyncio.wait_for(lifecycle.backend.check(), timeout=2)
                except Exception:
                    available = False
            return JSONResponse({"ready": available}, status_code=200 if available else 503)

        app = Starlette(
            routes=[Route("/health/live", live), Route("/health/ready", ready)]
            + create_agent_card_routes(agent_card)
            + create_jsonrpc_routes(request_handler, rpc_url="/", context_builder=AuthenticatedContextBuilder())
            + create_rest_routes(request_handler, context_builder=AuthenticatedContextBuilder()),
            lifespan=lifespan,
        )
        app.state.runtime = request_handler.runtime
        app.add_middleware(ProtocolMiddleware, auth_provider=self._auth, runtime_state=request_handler.runtime.state)

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

    def get_app(self):
        """Get the Starlette application without running it."""
        return self._build_app()

    def build_grpc_server(self, host: str = "0.0.0.0", port: int = 50051):
        """Build a configured (not yet started) grpc.aio server. EXPERIMENTAL.

        Uses the same skill executor and task store wiring as the HTTP app.
        The agent card served through this server advertises a GRPC
        AgentInterface pointing at host:port.

        Requires the optional grpc extra: pip install a2a-lite[grpc]

        Args:
            host: Bind address for the gRPC server.
            port: Port for the gRPC server.

        Returns:
            A managed server exposing the grpc.aio.Server API. Await
            server.start() / server.stop() to manage its lifecycle.
        """
        try:
            import grpc
            from a2a.server.request_handlers import GrpcHandler
            from a2a.types import a2a_pb2_grpc
        except ImportError as e:
            raise ImportError(
                "gRPC support is EXPERIMENTAL and requires extra dependencies. Install with: pip install a2a-lite[grpc]"
            ) from e

        display_host = "localhost" if host == "0.0.0.0" else host
        agent_card = self.build_agent_card(display_host, port, grpc_url=f"{display_host}:{port}")
        # This server only exposes gRPC; do not advertise unavailable HTTP ports.
        grpc_interface = agent_card.supported_interfaces[-1]
        del agent_card.supported_interfaces[:]
        agent_card.supported_interfaces.append(grpc_interface)
        agent_card.capabilities.extended_agent_card = True
        request_handler = self._build_request_handler(agent_card)
        request_handler.extended_agent_card = agent_card

        from .grpc import AuthenticatedGrpcContextBuilder, AuthInterceptor, ManagedGrpcServer

        server = grpc.aio.server(
            interceptors=[AuthInterceptor(self._auth, request_handler.runtime.state)],
            options=[
                ("grpc.max_receive_message_length", self._runtime_config.max_request_bytes),
                ("grpc.max_send_message_length", self._runtime_config.max_event_bytes),
            ],
        )
        a2a_pb2_grpc.add_A2AServiceServicer_to_server(
            GrpcHandler(request_handler, context_builder=AuthenticatedGrpcContextBuilder()), server
        )
        server.add_insecure_port(f"{host}:{port}")
        return ManagedGrpcServer(server, request_handler)

    def run_grpc(  # pragma: no cover
        self,
        host: str = "0.0.0.0",
        port: int = 50051,
    ) -> None:
        """Start an EXPERIMENTAL gRPC A2A server (blocking).

        Standalone transport: it does NOT serve the HTTP app, so the
        well-known agent card endpoint is not available here (the card is
        reachable over gRPC via GetExtendedAgentCard and advertises only
        the running gRPC interface).

        Requires: pip install a2a-lite[grpc]

        Simple:
            agent.run_grpc()

        With options:
            agent.run_grpc(port=50052)
        """
        display_host = "localhost" if host == "0.0.0.0" else host

        logger.warning("gRPC transport is EXPERIMENTAL - expect rough edges")
        logger.info("gRPC (experimental) server on %s:%d", display_host, port)

        async def _serve():
            # grpc.aio.server() binds to the running event loop at creation
            # time, so the server must be built inside the coroutine.
            server = self.build_grpc_server(host, port)

            try:
                await server.start()
                await server.wait_for_termination()
            finally:
                await server.stop(grace=2)

        try:
            asyncio.run(_serve())
        except KeyboardInterrupt:
            pass

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
