"""
Protected Skills - Google A2A SDK

These skills require authentication and integrate with the A2A SDK's
authentication system via RequestContext and ServerCallContext.
"""

from typing import Dict, Any, Optional
from a2a.server.agent_execution import RequestContext


class AuthenticationError(Exception):
    """Raised when authentication is required but missing."""
    pass


class AuthorizationError(Exception):
    """Raised when user lacks required permissions."""
    pass


def get_auth_context(context: RequestContext) -> Optional[Dict[str, Any]]:
    """
    Extract authentication context from RequestContext.
    
    Args:
        context: The RequestContext from the SDK
        
    Returns:
        Dict with auth info if authenticated, None otherwise
    """
    if not context or not context.call_context:
        return None
    
    call_context = context.call_context
    
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


def require_auth(context: RequestContext) -> Dict[str, Any]:
    """
    Require authentication from context or raise AuthenticationError.
    
    Args:
        context: The RequestContext from the SDK
        
    Returns:
        Dict with auth info
        
    Raises:
        AuthenticationError: If not authenticated
    """
    auth = get_auth_context(context)
    if not auth:
        raise AuthenticationError(
            "Authentication required. Use X-API-Key header or Authorization: Bearer token."
        )
    return auth


def require_permission(context: RequestContext, permission: str) -> Dict[str, Any]:
    """
    Require a specific permission from context.
    
    Args:
        context: The RequestContext from the SDK
        permission: The required permission
        
    Returns:
        Dict with auth info
        
    Raises:
        AuthenticationError: If not authenticated
        AuthorizationError: If missing required permission
    """
    auth = require_auth(context)
    permissions = auth.get('permissions', [])
    
    if permission not in permissions:
        raise AuthorizationError(
            f"Permission '{permission}' required. Your permissions: {permissions}"
        )
    
    return auth


def get_secret(context: RequestContext) -> Dict[str, Any]:
    """
    Return secret data - requires authentication.
    
    Args:
        context: RequestContext containing authentication info
        
    Returns:
        Secret data with auth details
        
    Raises:
        AuthenticationError: If user is not authenticated
    """
    auth = require_auth(context)
    
    return {
        "secret": "The answer is 42",
        "classified": "Project Phoenix is a go",
        "clearance_level": "top_secret",
        "accessed_by": auth['identity'],
        "auth_scheme": auth['scheme'],
        "permissions": auth['permissions'],
    }


def get_user_info(context: RequestContext) -> Dict[str, Any]:
    """
    Return information about the authenticated user.
    
    Args:
        context: RequestContext containing authentication info
        
    Returns:
        User information including identity, scheme, permissions, and roles
        
    Raises:
        AuthenticationError: If user is not authenticated
    """
    auth = require_auth(context)
    permissions = auth.get('permissions', [])
    
    # Map permissions to roles
    roles = []
    if 'read' in permissions:
        roles.append('viewer')
    if 'write' in permissions:
        roles.append('editor')
    if 'admin' in permissions:
        roles.append('administrator')
    
    return {
        "identity": auth['identity'],
        "authentication_scheme": auth['scheme'],
        "permissions": permissions,
        "roles": roles,
    }


def admin_only(context: RequestContext) -> Dict[str, Any]:
    """
    Return admin-only data - requires 'admin' permission.
    
    Args:
        context: RequestContext containing authentication info
        
    Returns:
        Admin-only system information
        
    Raises:
        AuthenticationError: If user is not authenticated
        AuthorizationError: If user lacks admin permission
    """
    auth = require_permission(context, 'admin')
    
    return {
        "system_status": "operational",
        "active_users": 42,
        "server_load": "34%",
        "last_backup": "2024-01-15T10:30:00Z",
        "accessed_by": auth['identity'],
        "message": "Welcome, administrator!",
        "admin_actions_available": [
            "view_logs",
            "manage_users",
            "system_config",
        ],
    }


def public_info(context: RequestContext) -> Dict[str, Any]:
    """
    Return public information - no authentication required.
    
    Args:
        context: RequestContext (auth not required)
        
    Returns:
        Public agent information
    """
    auth = get_auth_context(context)
    
    return {
        "agent_name": "SecureAgent",
        "version": "1.0.0",
        "status": "running",
        "authenticated": auth is not None,
        "identity": auth['identity'] if auth else None,
    }


# Skill registry mapping skill names to functions
SKILL_REGISTRY = {
    "get_secret": get_secret,
    "get_user_info": get_user_info,
    "admin_only": admin_only,
    "public_info": public_info,
}


def execute_skill(skill_name: str, context: RequestContext) -> Dict[str, Any]:
    """
    Execute a skill by name with the given context.
    
    Args:
        skill_name: Name of the skill to execute
        context: RequestContext containing authentication info
        
    Returns:
        Skill execution result
        
    Raises:
        ValueError: If skill doesn't exist
        AuthenticationError: If auth required but missing
        AuthorizationError: If permissions insufficient
    """
    if skill_name not in SKILL_REGISTRY:
        raise ValueError(
            f"Unknown skill: '{skill_name}'. "
            f"Available skills: {list(SKILL_REGISTRY.keys())}"
        )
    
    skill_func = SKILL_REGISTRY[skill_name]
    return skill_func(context)
