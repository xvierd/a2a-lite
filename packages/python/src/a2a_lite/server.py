"""Authentication and lifecycle adapters for the official A2A server."""

import asyncio
import base64
import json
from contextlib import asynccontextmanager

from a2a.auth.user import User
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.common import DefaultServerCallContextBuilder
from a2a.utils.errors import UnsupportedOperationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from .auth import AuthRequest, AuthResult, valid_identity


class AuthenticatedUser(User):
    def __init__(self, result: AuthResult, tenant: str = ""):
        self.result = result
        self.tenant = tenant

    @property
    def is_authenticated(self) -> bool:
        return self.result.authenticated and self.result.metadata.get("anonymous") is not True

    @property
    def user_name(self) -> str:
        principal = self.result.principal
        if not self.tenant:
            return principal
        payload = json.dumps(["owner", self.tenant, principal], ensure_ascii=False, separators=(",", ":"))
        return "a2a:v1:" + base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


class AuthenticatedContextBuilder(DefaultServerCallContextBuilder):
    def build(self, request):
        context = super().build(request)
        result = request.scope["a2a_lite.auth_result"]
        context.user = AuthenticatedUser(result)
        context.state["auth_result"] = result
        return context


class ProtocolMiddleware:
    """Authenticate all operations before the SDK reads or modifies any state."""

    def __init__(self, app, auth_provider, runtime_state=None):
        self.app = app
        self.auth_provider = auth_provider
        self.runtime_state = runtime_state

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Discovery stays public. OPTIONS is handled by CORS inside Starlette.
        if (
            scope["path"] in ("/.well-known/agent-card.json", "/health/live", "/health/ready")
            or scope["method"] == "OPTIONS"
        ):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        try:
            result = await self.auth_provider.authenticate(
                AuthRequest(
                    headers=dict(request.headers),
                    query_params=dict(request.query_params),
                    method=request.method,
                    path=request.url.path,
                )
            )
        except Exception:
            result = AuthResult.failure("Authentication required")
        if not valid_identity(result) or (
            self.runtime_state
            and self.runtime_state.config.profile != "learning"
            and result.metadata.get("anonymous") is True
        ):
            response = JSONResponse({"error": "Authentication required"}, status_code=401)
            await response(scope, receive, send)
            return
        if self.runtime_state:
            if self.runtime_state.config.profile == "durable" and not self.runtime_state.ready:
                await JSONResponse({"error": "Runtime is not ready"}, status_code=503)(scope, receive, send)
                return
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > self.runtime_state.config.max_request_bytes:
                    await JSONResponse({"error": "Request size limit exceeded"}, status_code=413)(scope, receive, send)
                    return
                if not message.get("more_body", False):
                    break
            original_receive = receive
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await original_receive()

            receive = bounded_receive
        scope["a2a_lite.auth_result"] = result

        async def send_protocol_response(message):
            # The SDK still labels HTTP+JSON error bodies application/json.
            # Normalize only REST responses, leaving JSON-RPC/card/SSE intact.
            if message["type"] == "http.response.start" and scope["path"] != "/":
                message = {
                    **message,
                    "headers": [
                        (name, b"application/a2a+json")
                        if name.lower() == b"content-type" and value == b"application/json"
                        else (name, value)
                        for name, value in message.get("headers", [])
                    ],
                }
            await send(message)

        await self.app(scope, receive, send_protocol_response)


class LiteRequestHandler(DefaultRequestHandler):
    def __init__(self, *, push_http_client, **kwargs):
        super().__init__(**kwargs)
        self._push_http_client = push_http_client
        self._lite_push_store = kwargs.get("push_config_store")
        self._push_lock = asyncio.Lock()

    @staticmethod
    def _authorize(context):
        result = context.state.get("auth_result")
        if not valid_identity(result) or context.tenant not in result.authorized_tenants:
            raise UnsupportedOperationError(message="Tenant is not authorized")
        # SDK stores resolve user_name only. Use a request-local copy so custom
        # stores also receive a tenant-scoped identity without altering skill auth.
        return context.model_copy(
            update={"user": AuthenticatedUser(result, context.tenant), "state": dict(context.state)}
        )

    async def on_get_task(self, params, context):
        return await super().on_get_task(params, self._authorize(context))

    async def on_list_tasks(self, params, context):
        return await super().on_list_tasks(params, self._authorize(context))

    async def on_cancel_task(self, params, context):
        from .recovery import CANCEL_KEY

        context = self._authorize(context)
        context.state[CANCEL_KEY] = True
        return await super().on_cancel_task(params, context)

    @asynccontextmanager
    async def _stream_slot(self):
        state = self.runtime.state
        if not state.accepting or state.streams >= state.config.max_streams:
            raise UnsupportedOperationError(message="Stream capacity exhausted")
        state.streams += 1
        try:
            yield
        finally:
            state.streams -= 1

    async def on_subscribe_to_task(self, params, context):
        context = self._authorize(context)
        async with self._stream_slot():
            async for event in super().on_subscribe_to_task(params, context):
                yield event

    async def on_get_extended_agent_card(self, params, context):
        return await super().on_get_extended_agent_card(params, self._authorize(context))

    @staticmethod
    def _require_push_identity(context):
        if not context.user.is_authenticated or not context.user.user_name.strip():
            raise UnsupportedOperationError(message="Per-task push notifications require authentication")

    async def on_message_send(self, params, context):
        context = self._authorize(context)
        if params.configuration.HasField("task_push_notification_config"):
            self._require_push_identity(context)
        return await super().on_message_send(params, context)

    async def on_message_send_stream(self, params, context):
        context = self._authorize(context)
        if params.configuration.HasField("task_push_notification_config"):
            self._require_push_identity(context)
        async with self._stream_slot():
            async for event in super().on_message_send_stream(params, context):
                yield event

    async def on_create_task_push_notification_config(self, params, context):
        context = self._authorize(context)
        self._require_push_identity(context)
        async with self._push_lock:
            configs = await self._lite_push_store.get_info(params.task_id, context=context)
            if len(configs) >= self.runtime.state.config.max_push_configs:
                raise UnsupportedOperationError(message="Push configuration limit exceeded")
            return await super().on_create_task_push_notification_config(params, context)

    async def on_get_task_push_notification_config(self, params, context):
        context = self._authorize(context)
        self._require_push_identity(context)
        return await super().on_get_task_push_notification_config(params, context)

    async def on_list_task_push_notification_configs(self, params, context):
        context = self._authorize(context)
        self._require_push_identity(context)
        return await super().on_list_task_push_notification_configs(params, context)

    async def on_delete_task_push_notification_config(self, params, context):
        context = self._authorize(context)
        self._require_push_identity(context)
        return await super().on_delete_task_push_notification_config(params, context)

    async def aclose(self):
        try:
            await super().aclose()
        finally:
            await self._push_http_client.aclose()
