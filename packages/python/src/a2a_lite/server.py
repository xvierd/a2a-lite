"""Authentication and lifecycle adapters for the official A2A server."""

from a2a.auth.user import User
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.common import DefaultServerCallContextBuilder
from a2a.utils.errors import UnsupportedOperationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from .auth import AuthRequest, AuthResult


class AuthenticatedUser(User):
    def __init__(self, result: AuthResult):
        self.result = result

    @property
    def is_authenticated(self) -> bool:
        return self.result.authenticated and self.result.metadata.get("anonymous") is not True

    @property
    def user_name(self) -> str:
        return self.result.user_id or ""


class AuthenticatedContextBuilder(DefaultServerCallContextBuilder):
    def build(self, request):
        context = super().build(request)
        result = request.scope["a2a_lite.auth_result"]
        context.user = AuthenticatedUser(result)
        context.state["auth_result"] = result
        return context


class ProtocolMiddleware:
    """Authenticate all operations before the SDK reads or modifies any state."""

    def __init__(self, app, auth_provider):
        self.app = app
        self.auth_provider = auth_provider

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Discovery stays public. OPTIONS is handled by CORS inside Starlette.
        if scope["path"] == "/.well-known/agent-card.json" or scope["method"] == "OPTIONS":
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
        if not result.authenticated or not isinstance(result.user_id, str) or not result.user_id.strip():
            response = JSONResponse({"error": "Authentication required"}, status_code=401)
            await response(scope, receive, send)
            return
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

    @staticmethod
    def _require_push_identity(context):
        if not context.user.is_authenticated or not context.user.user_name.strip():
            raise UnsupportedOperationError(message="Per-task push notifications require authentication")

    async def on_message_send(self, params, context):
        if params.configuration.HasField("task_push_notification_config"):
            self._require_push_identity(context)
        return await super().on_message_send(params, context)

    async def on_message_send_stream(self, params, context):
        if params.configuration.HasField("task_push_notification_config"):
            self._require_push_identity(context)
        async for event in super().on_message_send_stream(params, context):
            yield event

    async def on_create_task_push_notification_config(self, params, context):
        self._require_push_identity(context)
        return await super().on_create_task_push_notification_config(params, context)

    async def on_get_task_push_notification_config(self, params, context):
        self._require_push_identity(context)
        return await super().on_get_task_push_notification_config(params, context)

    async def on_list_task_push_notification_configs(self, params, context):
        self._require_push_identity(context)
        return await super().on_list_task_push_notification_configs(params, context)

    async def on_delete_task_push_notification_config(self, params, context):
        self._require_push_identity(context)
        return await super().on_delete_task_push_notification_config(params, context)

    async def aclose(self):
        try:
            await super().aclose()
        finally:
            await self._push_http_client.aclose()
