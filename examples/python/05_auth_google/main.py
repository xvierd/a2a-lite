"""
Secure Agent - Google A2A SDK Authentication Example

Demonstrates authentication implementation using the REAL Google A2A SDK:
- API Key authentication (header & query param)
- Bearer token authentication  
- Role-based access control
- Protected skills with authentication checks

SDK: a2a-sdk[http-server]

IMPORTANT: The A2A SDK uses Protobuf for wire format. The JSON structure differs
from the Pydantic models:
- Use "request" (not "message") for the message field
- Use "content" (not "parts") for message content (as an array)
- Use "ROLE_USER" / "ROLE_AGENT" (not "user" / "agent") for role enum
"""

import uuid
import uvicorn
from starlette.authentication import AuthenticationBackend, AuthCredentials
from starlette.middleware.authentication import AuthenticationMiddleware

from a2a.server.apps.rest import A2ARESTFastAPIApplication
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.events.in_memory_queue_manager import InMemoryQueueManager
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.apps.jsonrpc import DefaultCallContextBuilder
from a2a.server.context import User
from a2a.types import (
    AgentCard,
    AgentSkill,
    AgentCapabilities,
    APIKeySecurityScheme,
    HTTPAuthSecurityScheme,
    TaskStatus,
    TaskState,
    Artifact,
    TextPart,
    Message,
)

# =============================================================================
# DEMO CREDENTIALS (In production, use environment variables or a secure vault)
# =============================================================================
DEMO_API_KEYS = {
    "secret-key-123": {"identity": "api_user_1", "permissions": ["read"]},
    "client-key-456": {"identity": "api_user_2", "permissions": ["read", "write"]},
    "admin-key-789": {"identity": "admin_user", "permissions": ["read", "write", "admin"]},
}

DEMO_BEARER_TOKENS = {
    "valid-token-abc": {"identity": "bearer_user_1", "permissions": ["read", "write"]},
    "user-token-def": {"identity": "bearer_user_2", "permissions": ["read"]},
    "admin-token-ghi": {"identity": "admin_user", "permissions": ["read", "write", "admin"]},
}


# =============================================================================
# Custom AuthenticatedUser for SDK
# =============================================================================
class AuthenticatedUser(User):
    """Custom authenticated user implementing the A2A SDK User interface."""
    
    def __init__(self, identity: str, permissions: list[str], scheme: str):
        self._identity = identity
        self._permissions = permissions
        self._scheme = scheme
    
    @property
    def is_authenticated(self) -> bool:
        return True
    
    @property
    def user_name(self) -> str:
        return self._identity
    
    @property
    def display_name(self) -> str:
        """For Starlette compatibility."""
        return self._identity
    
    @property
    def permissions(self) -> list[str]:
        return self._permissions
    
    @property
    def scheme(self) -> str:
        return self._scheme


# =============================================================================
# Authentication Backend (Starlette)
# =============================================================================
class A2AAuthBackend(AuthenticationBackend):
    """
    Custom authentication backend for A2A requests.
    Supports API Key (header/query) and Bearer token authentication.
    """
    
    async def authenticate(self, conn):
        """Authenticate the request."""
        
        # Try API Key in header first
        api_key = conn.headers.get("X-API-Key")
        if api_key and api_key in DEMO_API_KEYS:
            user_info = DEMO_API_KEYS[api_key]
            return AuthCredentials(user_info["permissions"]), AuthenticatedUser(
                identity=user_info["identity"],
                permissions=user_info["permissions"],
                scheme="apiKey"
            )
        
        # Try API Key in query parameter
        api_key = conn.query_params.get("api_key")
        if api_key and api_key in DEMO_API_KEYS:
            user_info = DEMO_API_KEYS[api_key]
            return AuthCredentials(user_info["permissions"]), AuthenticatedUser(
                identity=user_info["identity"],
                permissions=user_info["permissions"],
                scheme="apiKey"
            )
        
        # Try Bearer token
        auth_header = conn.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
            if token in DEMO_BEARER_TOKENS:
                user_info = DEMO_BEARER_TOKENS[token]
                return AuthCredentials(user_info["permissions"]), AuthenticatedUser(
                    identity=user_info["identity"],
                    permissions=user_info["permissions"],
                    scheme="bearer"
                )
        
        return None


# =============================================================================
# Custom CallContextBuilder
# =============================================================================
class AuthCallContextBuilder(DefaultCallContextBuilder):
    """Builds ServerCallContext with authentication information."""
    
    def build(self, request) -> ServerCallContext:
        """Build context from request with auth info."""
        from a2a.server.apps.jsonrpc import StarletteUserProxy
        from a2a.server.context import UnauthenticatedUser
        from a2a.extensions.common import HTTP_EXTENSION_HEADER, get_requested_extensions
        
        user = UnauthenticatedUser()
        state: dict = {}
        
        try:
            # Try to get authenticated user from Starlette request
            if hasattr(request, 'user') and request.user.is_authenticated:
                user = StarletteUserProxy(request.user)
                # Add auth info to state
                state['auth'] = {
                    'identity': request.user.user_name,
                    'permissions': getattr(request.user, 'permissions', []),
                    'scheme': getattr(request.user, 'scheme', 'unknown'),
                }
        except Exception:
            pass
        
        state['headers'] = dict(request.headers)
        
        return ServerCallContext(
            user=user,
            state=state,
            requested_extensions=get_requested_extensions(
                request.headers.getlist(HTTP_EXTENSION_HEADER) if hasattr(request.headers, 'getlist') else []
            ),
        )


# =============================================================================
# AgentCard with Security Schemes
# =============================================================================
AGENT_CARD = AgentCard(
    name="SecureAgent",
    description="A secure agent requiring API Key or Bearer token authentication",
    version="1.0.0",
    url="http://localhost:8790/",
    capabilities=AgentCapabilities(
        streaming=False,
        push_notifications=False,
    ),
    default_input_modes=["text"],
    default_output_modes=["text"],
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
    ],
    security_schemes={
        "apiKeyAuth": APIKeySecurityScheme(
            type="apiKey",
            in_="header",
            name="X-API-Key",
            description="API Key authentication via X-API-Key header",
        ),
        "bearerAuth": HTTPAuthSecurityScheme(
            type="http",
            scheme="bearer",
            description="Bearer token authentication",
        ),
    },
    security=[
        {"apiKeyAuth": []},
        {"bearerAuth": []},
    ],
)


# =============================================================================
# Skills Implementation
# =============================================================================
class AuthenticationError(Exception):
    """Raised when authentication is required but missing."""
    pass


class AuthorizationError(Exception):
    """Raised when user lacks required permissions."""
    pass


def get_auth_context(context: RequestContext) -> dict | None:
    """Extract authentication context from RequestContext."""
    if not context or not context.call_context:
        return None
    return context.call_context.state.get('auth')


def get_secret(auth_context: dict | None) -> dict:
    """Get secret data - requires authentication."""
    if not auth_context:
        raise AuthenticationError("Authentication required")
    
    return {
        "secret": "The answer is 42",
        "classified": "Project Phoenix is a go",
        "accessed_by": auth_context.get("identity", "unknown"),
        "auth_scheme": auth_context.get("scheme", "unknown"),
        "permissions": auth_context.get("permissions", []),
    }


def get_user_info(auth_context: dict | None) -> dict:
    """Get information about the authenticated user."""
    if not auth_context:
        raise AuthenticationError("Authentication required")
    
    permissions = auth_context.get("permissions", [])
    roles = []
    if "read" in permissions:
        roles.append("viewer")
    if "write" in permissions:
        roles.append("editor")
    if "admin" in permissions:
        roles.append("administrator")
    
    return {
        "identity": auth_context.get("identity", "unknown"),
        "authentication_scheme": auth_context.get("scheme", "unknown"),
        "permissions": permissions,
        "roles": roles,
    }


def admin_only(auth_context: dict | None) -> dict:
    """Admin-only operation - requires 'admin' permission."""
    if not auth_context:
        raise AuthenticationError("Authentication required")
    
    permissions = auth_context.get("permissions", [])
    if "admin" not in permissions:
        raise AuthorizationError(f"Admin permission required. Your permissions: {permissions}")
    
    return {
        "system_status": "operational",
        "active_users": 42,
        "server_load": "34%",
        "accessed_by": auth_context.get("identity", "unknown"),
        "message": "Welcome, administrator!",
    }


SKILL_REGISTRY = {
    "get_secret": get_secret,
    "get_user_info": get_user_info,
    "admin_only": admin_only,
}


# =============================================================================
# Agent Executor
# =============================================================================
class SecureAgentExecutor(AgentExecutor):
    """Executor that implements the secure agent logic."""
    
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute skill based on the request context."""
        
        # Get user input (skill name from message)
        user_input = context.get_user_input().strip().lower()
        skill_name = user_input if user_input else "get_secret"
        
        # Get authentication context
        auth_context = get_auth_context(context)
        
        try:
            if skill_name in SKILL_REGISTRY:
                result = SKILL_REGISTRY[skill_name](auth_context)
                
                # Send success response as artifact
                await event_queue.enqueue_event(
                    Artifact(
                        artifact_id="result",
                        name="result",
                        parts=[TextPart(text=str(result))],
                    )
                )
                
                # Complete the task
                await event_queue.enqueue_event(
                    TaskStatus(
                        state=TaskState.completed,
                        message=Message(
                            message_id=str(uuid.uuid4()),
                            role="agent",
                            parts=[TextPart(text=f"Skill '{skill_name}' executed successfully.")],
                        ),
                    )
                )
            else:
                await event_queue.enqueue_event(
                    TaskStatus(
                        state=TaskState.failed,
                        message=Message(
                            message_id=str(uuid.uuid4()),
                            role="agent",
                            parts=[TextPart(text=f"Unknown skill: '{skill_name}'")],
                        ),
                    )
                )
        
        except AuthenticationError as e:
            await event_queue.enqueue_event(
                TaskStatus(
                    state=TaskState.auth_required,
                    message=Message(
                        message_id=str(uuid.uuid4()),
                        role="agent",
                        parts=[TextPart(text=f"Authentication Error: {str(e)}")],
                    ),
                )
            )
        
        except AuthorizationError as e:
            await event_queue.enqueue_event(
                TaskStatus(
                    state=TaskState.rejected,
                    message=Message(
                        message_id=str(uuid.uuid4()),
                        role="agent",
                        parts=[TextPart(text=f"Authorization Error: {str(e)}")],
                    ),
                )
            )
        
        except Exception as e:
            await event_queue.enqueue_event(
                TaskStatus(
                    state=TaskState.failed,
                    message=Message(
                        message_id=str(uuid.uuid4()),
                        role="agent",
                        parts=[TextPart(text=f"Error: {str(e)}")],
                    ),
                )
            )
    
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel task execution."""
        await event_queue.enqueue_event(
            TaskStatus(
                state=TaskState.canceled,
                message=Message(
                    message_id=str(uuid.uuid4()),
                    role="agent",
                    parts=[TextPart(text="Task canceled by user.")],
                ),
            )
        )


# =============================================================================
# Build and Run the Application
# =============================================================================
def create_app():
    """Create the FastAPI application with authentication."""
    
    # Create infrastructure components
    task_store = InMemoryTaskStore()
    queue_manager = InMemoryQueueManager()
    agent_executor = SecureAgentExecutor()
    
    # Create request handler
    handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=task_store,
        queue_manager=queue_manager,
    )
    
    # Build the A2A application
    a2a_app = A2ARESTFastAPIApplication(
        agent_card=AGENT_CARD,
        http_handler=handler,
        context_builder=AuthCallContextBuilder(),
    )
    
    app = a2a_app.build()
    
    # Add Starlette authentication middleware
    app.add_middleware(AuthenticationMiddleware, backend=A2AAuthBackend())
    
    return app


def main():
    """Run the secure agent server."""
    print("=" * 70)
    print("Secure Agent - Google A2A SDK (Authentication Demo)")
    print("=" * 70)
    print(f"Agent: {AGENT_CARD.name}")
    print(f"Description: {AGENT_CARD.description}")
    print(f"Version: {AGENT_CARD.version}")
    print(f"Skills: {[s.name for s in AGENT_CARD.skills]}")
    print("-" * 70)
    print("Security Schemes:")
    for scheme_id, scheme in AGENT_CARD.security_schemes.items():
        scheme_type = getattr(scheme, 'type', 'unknown')
        print(f"  - {scheme_id}: {scheme_type}")
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
    print("  - get_secret:   Requires authentication")
    print("  - get_user_info: Requires authentication")
    print("  - admin_only:   Requires admin permission")
    print("-" * 70)
    print("Agent Card: http://localhost:8790/.well-known/agent-card.json")
    print("A2A Endpoint: POST http://localhost:8790/v1/message:send")
    print("=" * 70)
    print()
    print("Example request:")
    print('  curl -X POST http://localhost:8790/v1/message:send \\')
    print('    -H "Content-Type: application/json" \\')
    print('    -H "X-API-Key: secret-key-123" \\')
    print('    -d \'{"request": {"messageId": "msg-1", "role": "ROLE_USER", "content": [{"text": "get_secret"}]}}\'')
    print()
    
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8790)


if __name__ == "__main__":
    main()
