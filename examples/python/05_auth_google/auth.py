"""
Authentication Components - Google A2A SDK (A2A v1.0)

This module provides authentication utilities that integrate with the
Google A2A SDK 1.x authentication flow:

  1. `AuthCallContextBuilder` (a ServerCallContextBuilder) inspects each
     HTTP request, validates credentials and builds a ServerCallContext
     carrying the authenticated user + auth metadata in `state['auth']`.
  2. The executor reads that context via `RequestContext.call_context`.

Supported credentials (demo):
  - API Key in header (X-API-Key)
  - API Key in query parameter (?api_key=...)
  - Bearer token (Authorization: Bearer <token>)
"""

from typing import Any, Dict, List, Optional

from starlette.requests import Request

from a2a.server.context import ServerCallContext, UnauthenticatedUser, User
from a2a.server.routes.common import DefaultServerCallContextBuilder


# =============================================================================
# Demo Credentials Database
# =============================================================================
DEMO_API_KEYS: Dict[str, Dict[str, Any]] = {
    "secret-key-123": {"identity": "api_user_1", "permissions": ["read"]},
    "client-key-456": {"identity": "api_user_2", "permissions": ["read", "write"]},
    "admin-key-789": {"identity": "admin_user", "permissions": ["read", "write", "admin"]},
}

DEMO_BEARER_TOKENS: Dict[str, Dict[str, Any]] = {
    "valid-token-abc": {"identity": "bearer_user_1", "permissions": ["read", "write"]},
    "user-token-def": {"identity": "bearer_user_2", "permissions": ["read"]},
    "admin-token-ghi": {"identity": "admin_user", "permissions": ["read", "write", "admin"]},
}


# =============================================================================
# Custom AuthenticatedUser for A2A SDK
# =============================================================================
class A2AAuthenticatedUser(User):
    """
    Custom authenticated user for the A2A SDK.

    Implements the SDK's User interface for proper integration
    with ServerCallContext.
    """

    def __init__(self, identity: str, permissions: List[str], scheme: str):
        self._identity = identity
        self._permissions = permissions
        self._scheme = scheme

    @property
    def is_authenticated(self) -> bool:
        """Returns True as this user is authenticated."""
        return True

    @property
    def user_name(self) -> str:
        """Returns the user's identity."""
        return self._identity

    @property
    def display_name(self) -> str:
        """Returns the user's display name (for Starlette compatibility)."""
        return self._identity

    @property
    def permissions(self) -> List[str]:
        """Returns the user's permissions."""
        return self._permissions

    @property
    def scheme(self) -> str:
        """Returns the authentication scheme used (apiKey or bearer)."""
        return self._scheme

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission."""
        return permission in self._permissions

    def __repr__(self) -> str:
        return f"A2AAuthenticatedUser(identity='{self._identity}', scheme='{self._scheme}')"


# =============================================================================
# Credential Validation
# =============================================================================
def validate_request(request: Request) -> Optional[Dict[str, Any]]:
    """
    Validate credentials on an incoming request.

    Returns:
        Dict with identity/permissions/scheme if credentials are valid,
        None otherwise.
    """
    # Try API Key in header first
    api_key = request.headers.get("X-API-Key")
    if api_key and api_key in DEMO_API_KEYS:
        info = DEMO_API_KEYS[api_key]
        return {**info, "scheme": "apiKey"}

    # Try API Key in query parameter
    api_key = request.query_params.get("api_key")
    if api_key and api_key in DEMO_API_KEYS:
        info = DEMO_API_KEYS[api_key]
        return {**info, "scheme": "apiKey"}

    # Try Bearer token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove "Bearer " prefix
        if token in DEMO_BEARER_TOKENS:
            info = DEMO_BEARER_TOKENS[token]
            return {**info, "scheme": "bearer"}

    return None


# =============================================================================
# Custom ServerCallContextBuilder
# =============================================================================
class AuthCallContextBuilder(DefaultServerCallContextBuilder):
    """
    Builds a ServerCallContext with authentication information.

    Passed to the route factories:

        create_jsonrpc_routes(handler, rpc_url="/", context_builder=AuthCallContextBuilder())
        create_rest_routes(handler, context_builder=AuthCallContextBuilder())
    """

    def build(self, request: Request) -> ServerCallContext:
        """Build context from request, adding validated auth info."""
        # Start from the default context (headers, extensions, starlette user)
        context = super().build(request)

        credentials = validate_request(request)
        if credentials:
            context.user = A2AAuthenticatedUser(
                identity=credentials["identity"],
                permissions=credentials["permissions"],
                scheme=credentials["scheme"],
            )
            context.state["auth"] = {
                "identity": credentials["identity"],
                "permissions": credentials["permissions"],
                "scheme": credentials["scheme"],
                "is_authenticated": True,
            }
        else:
            context.user = UnauthenticatedUser()

        return context


# =============================================================================
# Authentication Helper Functions
# =============================================================================
def get_auth_from_context(call_context: Any) -> Optional[Dict[str, Any]]:
    """
    Extract authentication information from ServerCallContext.

    Args:
        call_context: The ServerCallContext from the SDK

    Returns:
        Dict with auth info if authenticated, None otherwise
    """
    if not call_context:
        return None

    # Auth info populated by AuthCallContextBuilder
    if hasattr(call_context, "state") and "auth" in call_context.state:
        return call_context.state["auth"]

    # Fallback: derive from the user object
    user = getattr(call_context, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return {
            "identity": user.user_name,
            "permissions": getattr(user, "permissions", []),
            "scheme": getattr(user, "scheme", "unknown"),
            "is_authenticated": True,
        }

    return None


def require_auth(call_context: Any) -> Dict[str, Any]:
    """
    Require authentication from context or raise AuthenticationError.
    """
    auth = get_auth_from_context(call_context)
    if not auth:
        raise AuthenticationError(
            "Authentication required. Use X-API-Key header or Authorization: Bearer token."
        )
    return auth


def require_permission(call_context: Any, permission: str) -> Dict[str, Any]:
    """
    Require a specific permission from context.
    """
    auth = require_auth(call_context)
    permissions = auth.get("permissions", [])

    if permission not in permissions:
        raise AuthorizationError(
            f"Permission '{permission}' required. Your permissions: {permissions}"
        )

    return auth


# =============================================================================
# Custom Exceptions
# =============================================================================
class AuthenticationError(Exception):
    """Raised when authentication is required but missing or invalid."""
    pass


class AuthorizationError(Exception):
    """Raised when user lacks required permissions."""
    pass
