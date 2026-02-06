"""
Tests for authentication providers.
"""
import pytest
from a2a_lite.auth import (
    AuthRequest,
    AuthResult,
    NoAuth,
    APIKeyAuth,
    BearerAuth,
    CompositeAuth,
    require_auth,
)


class TestAuthResult:
    def test_success(self):
        result = AuthResult.success(user_id="user-123", scopes={"read", "write"})

        assert result.authenticated is True
        assert result.user_id == "user-123"
        assert "read" in result.scopes

    def test_failure(self):
        result = AuthResult.failure("Invalid token")

        assert result.authenticated is False
        assert result.error == "Invalid token"


class TestNoAuth:
    @pytest.mark.asyncio
    async def test_always_succeeds(self):
        auth = NoAuth()
        request = AuthRequest(headers={})

        result = await auth.authenticate(request)

        assert result.authenticated is True
        assert result.user_id == "anonymous"

    def test_empty_scheme(self):
        auth = NoAuth()
        assert auth.get_scheme() == {}


class TestAPIKeyAuth:
    @pytest.mark.asyncio
    async def test_valid_key_in_header(self):
        auth = APIKeyAuth(keys=["secret-key", "another-key"])
        request = AuthRequest(headers={"X-API-Key": "secret-key"})

        result = await auth.authenticate(request)

        assert result.authenticated is True
        assert result.user_id is not None

    @pytest.mark.asyncio
    async def test_invalid_key(self):
        auth = APIKeyAuth(keys=["secret-key"])
        request = AuthRequest(headers={"X-API-Key": "wrong-key"})

        result = await auth.authenticate(request)

        assert result.authenticated is False
        assert "Invalid" in result.error

    @pytest.mark.asyncio
    async def test_missing_key(self):
        auth = APIKeyAuth(keys=["secret-key"])
        request = AuthRequest(headers={})

        result = await auth.authenticate(request)

        assert result.authenticated is False
        assert "required" in result.error.lower()

    @pytest.mark.asyncio
    async def test_custom_header(self):
        auth = APIKeyAuth(keys=["key123"], header="Authorization")
        request = AuthRequest(headers={"Authorization": "key123"})

        result = await auth.authenticate(request)

        assert result.authenticated is True

    @pytest.mark.asyncio
    async def test_query_param(self):
        auth = APIKeyAuth(keys=["key123"], query_param="api_key")
        request = AuthRequest(headers={}, query_params={"api_key": "key123"})

        result = await auth.authenticate(request)

        assert result.authenticated is True

    def test_scheme(self):
        auth = APIKeyAuth(keys=["key"], header="X-API-Key")
        scheme = auth.get_scheme()

        assert scheme["type"] == "apiKey"
        assert scheme["in"] == "header"
        assert scheme["name"] == "X-API-Key"


class TestBearerAuth:
    @pytest.mark.asyncio
    async def test_valid_token(self):
        def validator(token):
            if token == "valid-token":
                return "user-123"
            return None

        auth = BearerAuth(validator=validator)
        request = AuthRequest(headers={"Authorization": "Bearer valid-token"})

        result = await auth.authenticate(request)

        assert result.authenticated is True
        assert result.user_id == "user-123"

    @pytest.mark.asyncio
    async def test_invalid_token(self):
        def validator(token):
            return None

        auth = BearerAuth(validator=validator)
        request = AuthRequest(headers={"Authorization": "Bearer invalid"})

        result = await auth.authenticate(request)

        assert result.authenticated is False

    @pytest.mark.asyncio
    async def test_missing_bearer_prefix(self):
        auth = BearerAuth(validator=lambda t: "user")
        request = AuthRequest(headers={"Authorization": "token-without-bearer"})

        result = await auth.authenticate(request)

        assert result.authenticated is False

    def test_scheme(self):
        auth = BearerAuth(validator=lambda t: None)
        scheme = auth.get_scheme()

        assert scheme["type"] == "http"
        assert scheme["scheme"] == "bearer"


class TestCompositeAuth:
    @pytest.mark.asyncio
    async def test_first_match_wins(self):
        auth = CompositeAuth([
            APIKeyAuth(keys=["api-key"]),
            BearerAuth(validator=lambda t: "bearer-user" if t == "token" else None),
        ])

        # API key should work
        request1 = AuthRequest(headers={"X-API-Key": "api-key"})
        result1 = await auth.authenticate(request1)
        assert result1.authenticated is True

        # Bearer should also work
        request2 = AuthRequest(headers={"Authorization": "Bearer token"})
        result2 = await auth.authenticate(request2)
        assert result2.authenticated is True

    @pytest.mark.asyncio
    async def test_all_fail(self):
        auth = CompositeAuth([
            APIKeyAuth(keys=["key1"]),
            APIKeyAuth(keys=["key2"]),
        ])

        request = AuthRequest(headers={"X-API-Key": "wrong"})
        result = await auth.authenticate(request)

        assert result.authenticated is False


class TestAuthIntegration:
    """Test that auth is actually enforced in the HTTP request pipeline."""

    def _make_agent_with_auth(self):
        from a2a_lite import Agent
        agent = Agent(
            name="SecureAgent",
            description="Auth integration test",
            auth=APIKeyAuth(keys=["valid-key"]),
        )

        @agent.skill("secret")
        async def secret(data: str) -> str:
            return f"secret: {data}"

        return agent

    def test_unauthenticated_request_rejected(self):
        """Requests without a valid API key should be rejected."""
        from starlette.testclient import TestClient
        import json
        from uuid import uuid4

        agent = self._make_agent_with_auth()
        app = agent.get_app()
        client = TestClient(app)

        request_body = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": uuid4().hex,
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": json.dumps({"skill": "secret", "params": {"data": "hello"}})}],
                    "messageId": uuid4().hex,
                }
            }
        }

        response = client.post("/", json=request_body)
        data = response.json()

        # The response should contain an auth error, not the skill result
        result_text = data.get("result", {}).get("parts", [{}])[0].get("text", "")
        assert "error" in result_text.lower() or "auth" in result_text.lower() or "key" in result_text.lower()
        assert "secret: hello" not in result_text

    def test_authenticated_request_succeeds(self):
        """Requests with a valid API key should succeed."""
        from starlette.testclient import TestClient
        import json
        from uuid import uuid4

        agent = self._make_agent_with_auth()
        app = agent.get_app()
        client = TestClient(app)

        request_body = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": uuid4().hex,
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": json.dumps({"skill": "secret", "params": {"data": "hello"}})}],
                    "messageId": uuid4().hex,
                }
            }
        }

        response = client.post(
            "/",
            json=request_body,
            headers={"X-API-Key": "valid-key"},
        )
        data = response.json()

        result_text = data.get("result", {}).get("parts", [{}])[0].get("text", "")
        assert "secret: hello" in result_text

    def test_wrong_key_rejected(self):
        """Requests with an invalid API key should be rejected."""
        from starlette.testclient import TestClient
        import json
        from uuid import uuid4

        agent = self._make_agent_with_auth()
        app = agent.get_app()
        client = TestClient(app)

        request_body = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": uuid4().hex,
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": json.dumps({"skill": "secret", "params": {"data": "hello"}})}],
                    "messageId": uuid4().hex,
                }
            }
        }

        response = client.post(
            "/",
            json=request_body,
            headers={"X-API-Key": "wrong-key"},
        )
        data = response.json()

        result_text = data.get("result", {}).get("parts", [{}])[0].get("text", "")
        assert "secret: hello" not in result_text


class TestRequireAuth:
    """Test that require_auth decorator receives AuthResult from executor."""

    def test_require_auth_receives_auth_result(self):
        """Skills decorated with require_auth should receive the AuthResult."""
        from a2a_lite import Agent
        from a2a_lite.testing import AgentTestClient
        from starlette.testclient import TestClient
        import json
        from uuid import uuid4

        agent = Agent(
            name="AuthTest",
            description="require_auth test",
            auth=APIKeyAuth(keys=["my-key"]),
        )

        @agent.skill("admin")
        @require_auth(scopes=["admin"])
        async def admin_action(data: str, auth: AuthResult) -> str:
            return f"admin:{auth.user_id}:{data}"

        app = agent.get_app()
        client = TestClient(app)

        # Without auth — should be rejected at the gate
        request_body = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": uuid4().hex,
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": json.dumps({"skill": "admin", "params": {"data": "hello"}})}],
                    "messageId": uuid4().hex,
                }
            }
        }
        response = client.post("/", json=request_body)
        result_text = response.json().get("result", {}).get("parts", [{}])[0].get("text", "")
        assert "admin:" not in result_text

        # With valid auth — require_auth checks scopes (no admin scope, so should fail)
        response = client.post("/", json=request_body, headers={"X-API-Key": "my-key"})
        result_text = response.json().get("result", {}).get("parts", [{}])[0].get("text", "")
        assert "Insufficient permissions" in result_text or "error" in result_text.lower()

    def test_auth_param_injected_without_decorator(self):
        """Skills with auth: AuthResult parameter should receive it directly."""
        from a2a_lite import Agent
        from starlette.testclient import TestClient
        import json
        from uuid import uuid4

        agent = Agent(
            name="AuthTest2",
            description="auth param test",
            auth=APIKeyAuth(keys=["my-key"]),
        )

        @agent.skill("whoami")
        async def whoami(auth: AuthResult) -> str:
            return f"user:{auth.user_id}"

        app = agent.get_app()
        client = TestClient(app)

        request_body = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": uuid4().hex,
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": json.dumps({"skill": "whoami", "params": {}})}],
                    "messageId": uuid4().hex,
                }
            }
        }

        response = client.post("/", json=request_body, headers={"X-API-Key": "my-key"})
        result_text = response.json().get("result", {}).get("parts", [{}])[0].get("text", "")
        assert result_text.startswith("user:")
