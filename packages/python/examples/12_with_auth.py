"""
Example: Authentication (optional).

Add auth when you need it - skip it when you don't.

Run: python examples/12_with_auth.py
Test: curl -H "X-API-Key: secret-key" http://localhost:8787/...
"""
from a2a_lite import Agent, APIKeyAuth

# Simple API key auth
agent = Agent(
    name="SecureBot",
    description="Bot with authentication",
    auth=APIKeyAuth(
        keys=["secret-key", "another-key"],
        header="X-API-Key",
    ),
)


@agent.skill("public_info")
async def public_info() -> dict:
    """This skill is available to authenticated users."""
    return {"message": "You're authenticated!"}


@agent.skill("get_secrets")
async def get_secrets() -> dict:
    """Get secret data (requires auth)."""
    return {
        "secrets": ["secret1", "secret2"],
        "message": "Only authenticated users can see this",
    }


if __name__ == "__main__":
    print("Test with: curl -H 'X-API-Key: secret-key' http://localhost:8787/")
    agent.run(port=8787)


# More auth options:
#
# Bearer Token:
#   from a2a_lite import BearerAuth
#   auth = BearerAuth(validator=lambda token: verify_jwt(token))
#
# OAuth2/OIDC:
#   from a2a_lite import OAuth2Auth
#   auth = OAuth2Auth(
#       issuer="https://auth.company.com",
#       audience="my-agent",
#   )
