"""
Secure Agent - A2A Lite Implementation

Demonstrates simplified authentication with A2A Lite.
Compare this ~60 line implementation with the ~374 line Google SDK version.
"""

from a2a_lite import Agent, APIKeyAuth, BearerAuth
from a2a_lite.auth import AuthResult, CompositeAuth

# Create authentication provider
# A2A Lite handles all the hashing, validation, and security automatically
auth_provider = CompositeAuth([
    APIKeyAuth(
        keys=["secret-key-123", "client-key-456", "test-key-789"],
        header="X-API-Key"
    ),
    BearerAuth(
        tokens=["valid-token-abc", "user-token-def", "admin-token-ghi"]
    )
])

# Create secure agent with authentication
agent = Agent(
    name="SecureAgent",
    description="A secure agent requiring authentication",
    version="1.0.0",
    auth=auth_provider  # Single line for full auth setup!
)


@agent.skill("get_secret")
async def get_secret() -> dict:
    """Get secret data - requires authentication."""
    return {
        "secret": "The answer is 42",
        "classified": "Project Phoenix is a go",
        "clearance_level": "top_secret"
    }


@agent.skill("whoami")
async def whoami(auth: AuthResult) -> dict:
    """
    Get current user information.
    
    The auth parameter is auto-injected by A2A Lite when type-hinted!
    """
    return {
        "identity": auth.identity,
        "scheme": auth.scheme,
        "permissions": auth.permissions,
        "authenticated": True
    }


@agent.skill("admin_only")
async def admin_only(auth: AuthResult) -> dict:
    """
    Admin-only endpoint.
    
    Demonstrates permission checking.
    """
    if "admin" not in auth.permissions:
        # A2A Lite automatically converts this to 403 Forbidden
        raise PermissionError("Admin permission required")
    
    return {
        "system_status": "operational",
        "active_users": 42,
        "server_load": "34%",
        "message": "Welcome, administrator!"
    }


@agent.skill("public_info")
async def public_info() -> dict:
    """
    Public endpoint - no authentication required.
    
    Skills without auth parameter work normally.
    """
    return {
        "agent_name": "SecureAgent",
        "version": "1.0.0",
        "public_data": "This is visible to everyone"
    }


if __name__ == "__main__":
    print("=" * 70)
    print("Secure Agent - A2A Lite (Authentication Demo)")
    print("=" * 70)
    print("Agent: SecureAgent")
    print("Port: 8790")
    print("-" * 70)
    print("Authentication Methods:")
    print("  1. API Key Header: X-API-Key: <key>")
    print("  2. Bearer Token: Authorization: Bearer <token>")
    print("-" * 70)
    print("Demo Credentials:")
    print("  API Keys: secret-key-123, client-key-456, test-key-789")
    print("  Bearer: valid-token-abc, user-token-def, admin-token-ghi")
    print("-" * 70)
    print("Skills:")
    print("  - get_secret: Requires auth")
    print("  - whoami: Returns auth info (auto-injected)")
    print("  - admin_only: Requires admin permission")
    print("  - public_info: No auth required")
    print("=" * 70)
    print("\nA2A Lite handles:")
    print("  ✓ SHA-256 key hashing (automatic)")
    print("  ✓ Timing-safe comparison")
    print("  ✓ 401/403 error responses")
    print("  ✓ Auth context injection")
    print("=" * 70)
    
    agent.run(port=8790)
