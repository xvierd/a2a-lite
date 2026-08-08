"""
Unit tests for Secure Agent using A2A Lite's TestClient.

Demonstrates testing authenticated agents without HTTP.
"""

import pytest
from agent import agent
from a2a_lite import AgentTestClient


def test_public_endpoint_no_auth():
    """public_info needs no specific identity, but the agent's global auth
    still requires valid credentials for every request."""
    client = AgentTestClient(
        agent,
        headers={"X-API-Key": "secret-key-123"}
    )
    
    result = client.call("public_info")
    assert result.data["agent_name"] == "SecureAgent"
    assert "public_data" in result.data


def test_protected_endpoint_without_auth():
    """Protected endpoint should fail without auth."""
    client = AgentTestClient(agent)
    
    # A2A Lite returns auth failures as a structured error message
    result = client.call("get_secret")
    assert "error" in result.data
    assert "authentication" in result.data["error"].lower()


def test_protected_endpoint_with_api_key():
    """Protected endpoint should work with valid API key."""
    client = AgentTestClient(
        agent,
        headers={"X-API-Key": "secret-key-123"}
    )
    
    result = client.call("get_secret")
    assert result.data["secret"] == "The answer is 42"


def test_protected_endpoint_with_bearer_token():
    """Protected endpoint should work with valid Bearer token."""
    client = AgentTestClient(
        agent,
        headers={"Authorization": "Bearer valid-token-abc"}
    )
    
    result = client.call("get_secret")
    assert result.data["secret"] == "The answer is 42"


def test_whoami_returns_auth_info():
    """whoami skill should return authentication details."""
    client = AgentTestClient(
        agent,
        headers={"X-API-Key": "secret-key-123"}
    )
    
    result = client.call("whoami")
    assert "identity" in result.data
    assert result.data["authenticated"] is True


def test_admin_only_with_regular_user():
    """Admin endpoint should fail for non-admin users."""
    # Regular API key doesn't map to the admin identity
    client = AgentTestClient(
        agent,
        headers={"X-API-Key": "secret-key-123"}
    )
    
    result = client.call("admin_only")
    assert "admin" in result.data["error"].lower()


def test_admin_only_with_admin_token():
    """Admin endpoint should work for admin users."""
    client = AgentTestClient(
        agent,
        headers={"Authorization": "Bearer admin-token-ghi"}
    )
    
    result = client.call("admin_only")
    assert "system_status" in result.data
    assert "Welcome, administrator" in result.data["message"]


def test_invalid_api_key():
    """Invalid API key should be rejected."""
    client = AgentTestClient(
        agent,
        headers={"X-API-Key": "invalid-key"}
    )
    
    result = client.call("get_secret")
    assert "error" in result.data


def test_invalid_bearer_token():
    """Invalid Bearer token should be rejected."""
    client = AgentTestClient(
        agent,
        headers={"Authorization": "Bearer invalid-token"}
    )
    
    result = client.call("get_secret")
    assert "error" in result.data


if __name__ == "__main__":
    print("Running authentication tests...")
    
    tests = [
        ("Public endpoint (no auth)", test_public_endpoint_no_auth),
        ("Protected without auth", test_protected_endpoint_without_auth),
        ("Protected with API key", test_protected_endpoint_with_api_key),
        ("Protected with Bearer", test_protected_endpoint_with_bearer_token),
        ("Whoami returns auth", test_whoami_returns_auth_info),
        ("Admin-only (regular user)", test_admin_only_with_regular_user),
        ("Admin-only (admin)", test_admin_only_with_admin_token),
        ("Invalid API key", test_invalid_api_key),
        ("Invalid Bearer", test_invalid_bearer_token),
    ]
    
    for name, test_func in tests:
        try:
            test_func()
            print(f"✓ {name}")
        except Exception as e:
            print(f"✗ {name}: {e}")
    
    print("\nAll tests completed!")
