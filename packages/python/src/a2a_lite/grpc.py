"""Optional gRPC authentication and server lifecycle adapters."""

from contextvars import ContextVar

import grpc
from a2a.server.request_handlers.grpc_handler import DefaultGrpcServerCallContextBuilder

from .auth import AuthRequest, AuthResult, valid_identity
from .server import AuthenticatedUser

_auth_result: ContextVar[AuthResult] = ContextVar("a2a_lite.grpc.auth_result")


class AuthenticatedGrpcContextBuilder(DefaultGrpcServerCallContextBuilder):
    def build(self, context):
        call_context = super().build(context)
        result = _auth_result.get()
        call_context.user = AuthenticatedUser(result)
        call_context.state["auth_result"] = result
        return call_context


class AuthInterceptor(grpc.aio.ServerInterceptor):
    def __init__(self, provider, runtime_state=None):
        self.provider = provider
        self.runtime_state = runtime_state

    async def intercept_service(self, continuation, handler_call_details):
        handler = await continuation(handler_call_details)
        if handler is None:
            return None

        async def authenticate(context):
            try:
                result = await self.provider.authenticate(
                    AuthRequest(
                        headers=dict(context.invocation_metadata()),
                        path=handler_call_details.method,
                    )
                )
            except Exception:
                result = AuthResult.failure("Authentication required")
            if not valid_identity(result) or (
                self.runtime_state
                and self.runtime_state.config.profile != "learning"
                and result.metadata.get("anonymous") is True
            ):
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Authentication required")
            return _auth_result.set(result)

        if handler.unary_unary:

            async def unary(request, context):
                token = await authenticate(context)
                try:
                    return await handler.unary_unary(request, context)
                finally:
                    _auth_result.reset(token)

            return grpc.unary_unary_rpc_method_handler(
                unary,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        if handler.unary_stream:

            async def stream(request, context):
                token = await authenticate(context)
                try:
                    async for event in handler.unary_stream(request, context):
                        yield event
                finally:
                    _auth_result.reset(token)

            return grpc.unary_stream_rpc_method_handler(
                stream,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        return handler


class ManagedGrpcServer:
    """Delegate the gRPC server API while draining SDK work during stop()."""

    def __init__(self, server, request_handler):
        self._server = server
        self._request_handler = request_handler

    def __getattr__(self, name):
        return getattr(self._server, name)

    async def start(self):
        await self._request_handler.runtime.start()
        try:
            await self._server.start()
        except BaseException:
            await self._request_handler.runtime.stop()
            raise

    @property
    def stats(self):
        return self._request_handler.runtime.state.snapshot()

    async def stop(self, grace=None):
        try:
            await self._server.stop(grace)
        finally:
            await self._request_handler.runtime.stop()
