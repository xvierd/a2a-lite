"""
Secure Agent - Google A2A SDK Authentication Example (A2A v1.0)

Demonstrates authentication using the official Google A2A SDK 1.x:
- API Key authentication (header & query param)
- Bearer token authentication
- Role-based access control (permissions)
- Protected skills with authentication checks

Key v1.0 pieces:
- ServerCallContext comes from a2a.server.context
- Auth runs in a custom ServerCallContextBuilder (auth.py), passed to the
  route factories - no Starlette middleware needed.
- Non-streaming executor: exactly ONE Message per request.

SDK: a2a-sdk[http-server]>=1.1.2

Wire format (v1.0 JSON-RPC):
  {"jsonrpc": "2.0", "id": "1", "method": "SendMessage",
   "params": {"message": {"role": "ROLE_USER", "messageId": "m1",
                          "parts": [{"text": "get_secret"}]}}}
  + header "A2A-Version: 1.0"
"""

import json
import os

import uvicorn
from starlette.applications import Starlette

from a2a.helpers import new_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    create_agent_card_routes,
    create_jsonrpc_routes,
    create_rest_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    APIKeySecurityScheme,
    HTTPAuthSecurityScheme,
    SecurityRequirement,
    SecurityScheme,
    StringList,
)

from auth import (
    AuthCallContextBuilder,
    AuthenticationError,
    AuthorizationError,
)
from skills import execute_skill

AGENT_URL = "http://localhost:8790/"


# =============================================================================
# AgentCard with Security Schemes (v1.0 proto types)
# =============================================================================
AGENT_CARD = AgentCard(
    name="SecureAgent",
    description="A secure agent requiring API Key or Bearer token authentication",
    version="1.0.0",
    supported_interfaces=[
        AgentInterface(
            url=AGENT_URL,
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        ),
    ],
    capabilities=AgentCapabilities(
        streaming=False,
        push_notifications=False,
    ),
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    skills=[
        AgentSkill(
            id="get_secret",
            name="get_secret",
            description="Get secret data (requires authentication)",
            tags=["secure", "secret"],
        ),
        AgentSkill(
            id="get_user_info",
            name="get_user_info",
            description="Get current user authentication info",
            tags=["auth", "user"],
        ),
        AgentSkill(
            id="admin_only",
            name="admin_only",
            description="Admin-only operation (requires admin permission)",
            tags=["admin", "restricted"],
        ),
        AgentSkill(
            id="public_info",
            name="public_info",
            description="Public agent information (no auth required)",
            tags=["public"],
        ),
    ],
    security_schemes={
        "apiKeyAuth": SecurityScheme(
            api_key_security_scheme=APIKeySecurityScheme(
                description="API Key authentication via X-API-Key header",
                location="header",
                name="X-API-Key",
            )
        ),
        "bearerAuth": SecurityScheme(
            http_auth_security_scheme=HTTPAuthSecurityScheme(
                description="Bearer token authentication",
                scheme="bearer",
            )
        ),
    },
    security_requirements=[
        SecurityRequirement(schemes={"apiKeyAuth": StringList(list=[])}),
        SecurityRequirement(schemes={"bearerAuth": StringList(list=[])}),
    ],
)


# =============================================================================
# Agent Executor
# =============================================================================
class SecureAgentExecutor(AgentExecutor):
    """
    Executor that implements the secure agent logic.

    Non-streaming: every request produces exactly one Message containing
    a JSON payload (result or structured error).
    """

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute skill based on the request context."""
        user_input = context.get_user_input().strip().lower()
        skill_name = user_input if user_input else "get_secret"

        try:
            result = execute_skill(skill_name, context)
            await event_queue.enqueue_event(new_text_message(json.dumps(result)))

        except AuthenticationError as e:
            await event_queue.enqueue_event(new_text_message(json.dumps({
                "error": str(e),
                "type": "AuthenticationError",
                "hint": "Authenticate with X-API-Key header or Authorization: Bearer <token>",
            })))

        except AuthorizationError as e:
            await event_queue.enqueue_event(new_text_message(json.dumps({
                "error": str(e),
                "type": "AuthorizationError",
            })))

        except ValueError as e:
            await event_queue.enqueue_event(new_text_message(json.dumps({
                "error": str(e),
                "type": "UnknownSkill",
            })))

        except Exception as e:
            await event_queue.enqueue_event(new_text_message(json.dumps({
                "error": f"Internal error: {e}",
                "type": type(e).__name__,
            })))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel task execution (no long-running tasks in this agent)."""
        pass


# =============================================================================
# Build and Run the Application
# =============================================================================
def create_app() -> Starlette:
    """Create the Starlette application with authentication."""
    task_store = InMemoryTaskStore()
    agent_executor = SecureAgentExecutor()

    handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=task_store,
        agent_card=AGENT_CARD,
    )

    # The auth-aware context builder validates credentials per request and
    # exposes them via RequestContext.call_context.state['auth']
    context_builder = AuthCallContextBuilder()

    return Starlette(
        routes=create_agent_card_routes(AGENT_CARD)
        + create_jsonrpc_routes(handler, rpc_url="/", context_builder=context_builder)
        + create_rest_routes(handler, context_builder=context_builder)
    )


def main():
    """Run the secure agent server."""
    print("=" * 70)
    print("Secure Agent - Google A2A SDK (Authentication Demo) - A2A v1.0")
    print("=" * 70)
    print(f"Agent: {AGENT_CARD.name}")
    print(f"Description: {AGENT_CARD.description}")
    print(f"Version: {AGENT_CARD.version}")
    print(f"Skills: {[s.name for s in AGENT_CARD.skills]}")
    print("-" * 70)
    print("Authentication Methods:")
    print("  1. API Key Header: X-API-Key: secret-key-123")
    print("  2. API Key Query:  ?api_key=secret-key-123")
    print("  3. Bearer Token:   Authorization: Bearer valid-token-abc")
    print("-" * 70)
    print("Demo Credentials:")
    print("  API Keys:    secret-key-123 (read), client-key-456 (read+write), admin-key-789 (admin)")
    print("  Bearer Tokens: valid-token-abc (read+write), user-token-def (read), admin-token-ghi (admin)")
    print("-" * 70)
    print("Protected Skills:")
    print("  - get_secret:    Requires authentication")
    print("  - get_user_info: Requires authentication")
    print("  - admin_only:    Requires admin permission")
    print("  - public_info:   No auth required")
    print("-" * 70)
    print("Agent Card: http://localhost:8790/.well-known/agent-card.json")
    print("A2A Endpoint: POST http://localhost:8790/ (JSON-RPC SendMessage)")
    print("=" * 70)
    print()
    print("Example request:")
    print('  curl -X POST http://localhost:8790/ \\')
    print('    -H "Content-Type: application/json" \\')
    print('    -H "A2A-Version: 1.0" \\')
    print('    -H "X-API-Key: secret-key-123" \\')
    print('    -d \'{"jsonrpc": "2.0", "id": "1", "method": "SendMessage", "params": {"message": {"role": "ROLE_USER", "messageId": "msg-1", "parts": [{"text": "get_secret"}]}}}\'')
    print()

    app = create_app()
    port = int(os.getenv("PORT", "8790"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
