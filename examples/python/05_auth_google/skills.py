"""
Protected Skills - Google A2A SDK (A2A v1.0)

These skills require authentication and integrate with the A2A SDK's
authentication system via RequestContext -> ServerCallContext.

The auth info is populated per-request by AuthCallContextBuilder
(see auth.py) into call_context.state['auth'].
"""

from typing import Any, Dict, Optional

from a2a.server.agent_execution import RequestContext

from auth import (
    AuthenticationError,
    AuthorizationError,
    get_auth_from_context,
    require_auth,
    require_permission,
)


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
    return get_auth_from_context(context.call_context)


def get_secret(context: RequestContext) -> Dict[str, Any]:
    """
    Return secret data - requires authentication.
    """
    auth = require_auth(context.call_context)

    return {
        "secret": "The answer is 42",
        "classified": "Project Phoenix is a go",
        "clearance_level": "top_secret",
        "accessed_by": auth["identity"],
        "auth_scheme": auth["scheme"],
        "permissions": auth["permissions"],
    }


def get_user_info(context: RequestContext) -> Dict[str, Any]:
    """
    Return information about the authenticated user.
    """
    auth = require_auth(context.call_context)
    permissions = auth.get("permissions", [])

    # Map permissions to roles
    roles = []
    if "read" in permissions:
        roles.append("viewer")
    if "write" in permissions:
        roles.append("editor")
    if "admin" in permissions:
        roles.append("administrator")

    return {
        "identity": auth["identity"],
        "authentication_scheme": auth["scheme"],
        "permissions": permissions,
        "roles": roles,
    }


def admin_only(context: RequestContext) -> Dict[str, Any]:
    """
    Return admin-only data - requires 'admin' permission.
    """
    auth = require_permission(context.call_context, "admin")

    return {
        "system_status": "operational",
        "active_users": 42,
        "server_load": "34%",
        "last_backup": "2024-01-15T10:30:00Z",
        "accessed_by": auth["identity"],
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
    """
    auth = get_auth_context(context)

    return {
        "agent_name": "SecureAgent",
        "version": "1.0.0",
        "status": "running",
        "authenticated": auth is not None,
        "identity": auth["identity"] if auth else None,
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
    """
    if skill_name not in SKILL_REGISTRY:
        raise ValueError(
            f"Unknown skill: '{skill_name}'. "
            f"Available skills: {list(SKILL_REGISTRY.keys())}"
        )

    return SKILL_REGISTRY[skill_name](context)
