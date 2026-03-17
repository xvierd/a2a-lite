"""
Authentication Components - Google A2A SDK

This module provides authentication utilities that integrate with the
Google A2A SDK's authentication system.

Uses Starlette's authentication backend for seamless integration
with the A2A SDK's ServerCallContext.
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from starlette.authentication import AuthenticationBackend, AuthCredentials, SimpleUser
from starlette.requests import HTTPConnection

from a2a.server.context import User


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
# Authentication Backend
# =============================================================================
class A2AAuthBackend(AuthenticationBackend):
    """
    Starlette authentication backend for A2A requests.
    
    Supports:
    - API Key in header (X-API-Key)
    - API Key in query parameter (?api_key=...)
    - Bearer token in Authorization header (Authorization: Bearer <token>)
    
    Usage:
        from starlette.middleware.authentication import AuthenticationMiddleware
        app.add_middleware(AuthenticationMiddleware, backend=A2AAuthBackend())
    """
    
    def __init__(
        self,
        api_keys: Optional[Dict[str, Dict[str, Any]]] = None,
        bearer_tokens: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        """
        Initialize the authentication backend.
        
        Args:
            api_keys: Dict mapping API keys to user info dicts
            bearer_tokens: Dict mapping bearer tokens to user info dicts
        """
        self.api_keys = api_keys or DEMO_API_KEYS
        self.bearer_tokens = bearer_tokens or DEMO_BEARER_TOKENS
    
    async def authenticate(self, conn: HTTPConnection) -> Optional[tuple[AuthCredentials, A2AAuthenticatedUser]]:
        """
        Authenticate the HTTP connection.
        
        Args:
            conn: The HTTP connection (request)
            
        Returns:
            Tuple of (AuthCredentials, User) if authenticated, None otherwise
        """
        # Try API Key in header first
        api_key = conn.headers.get("X-API-Key")
        if api_key and api_key in self.api_keys:
            user_info = self.api_keys[api_key]
            return (
                AuthCredentials(user_info["permissions"]),
                A2AAuthenticatedUser(
                    identity=user_info["identity"],
                    permissions=user_info["permissions"],
                    scheme="apiKey"
                )
            )
        
        # Try API Key in query parameter
        api_key = conn.query_params.get("api_key")
        if api_key and api_key in self.api_keys:
            user_info = self.api_keys[api_key]
            return (
                AuthCredentials(user_info["permissions"]),
                A2AAuthenticatedUser(
                    identity=user_info["identity"],
                    permissions=user_info["permissions"],
                    scheme="apiKey"
                )
            )
        
        # Try Bearer token
        auth_header = conn.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
            if token in self.bearer_tokens:
                user_info = self.bearer_tokens[token]
                return (
                    AuthCredentials(user_info["permissions"]),
                    A2AAuthenticatedUser(
                        identity=user_info["identity"],
                        permissions=user_info["permissions"],
                        scheme="bearer"
                    )
                )
        
        # No valid authentication found - return None to indicate unauthenticated
        return None


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
    
    # Check if user is authenticated
    if hasattr(call_context, 'user') and call_context.user.is_authenticated:
        user = call_context.user
        return {
            'identity': user.user_name,
            'permissions': getattr(user, 'permissions', []),
            'scheme': getattr(user, 'scheme', 'unknown'),
            'is_authenticated': True,
        }
    
    # Check state for auth info (fallback)
    if hasattr(call_context, 'state') and 'auth' in call_context.state:
        return call_context.state['auth']
    
    return None


def require_auth(call_context: Any) -> Dict[str, Any]:
    """
    Require authentication from context or raise AuthenticationError.
    
    Args:
        call_context: The ServerCallContext from the SDK
        
    Returns:
        Dict with auth info
        
    Raises:
        AuthenticationError: If not authenticated
    """
    auth = get_auth_from_context(call_context)
    if not auth:
        raise AuthenticationError("Authentication required. Use X-API-Key header or Authorization: Bearer token.")
    return auth


def require_permission(call_context: Any, permission: str) -> Dict[str, Any]:
    """
    Require a specific permission from context.
    
    Args:
        call_context: The ServerCallContext from the SDK
        permission: The required permission
        
    Returns:
        Dict with auth info
        
    Raises:
        AuthenticationError: If not authenticated
        AuthorizationError: If missing required permission
    """
    auth = require_auth(call_context)
    permissions = auth.get('permissions', [])
    
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


# =============================================================================
# Factory Function
# =============================================================================
def create_auth_backend(
    api_keys: Optional[Dict[str, Dict[str, Any]]] = None,
    bearer_tokens: Optional[Dict[str, Dict[str, Any]]] = None,
) -> A2AAuthBackend:
    """
    Create an authentication backend with custom or default credentials.
    
    Args:
        api_keys: Custom API keys dict (uses DEMO_API_KEYS if None)
        bearer_tokens: Custom bearer tokens dict (uses DEMO_BEARER_TOKENS if None)
        
    Returns:
        Configured A2AAuthBackend instance
    """
    return A2AAuthBackend(
        api_keys=api_keys or DEMO_API_KEYS,
        bearer_tokens=bearer_tokens or DEMO_BEARER_TOKENS,
    )
