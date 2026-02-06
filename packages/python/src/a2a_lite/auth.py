"""
Authentication support (OPTIONAL).

By default, A2A Lite agents have no authentication.
Add auth when you need it for enterprise deployments.

Example (simple - no auth):
    agent = Agent(name="Bot", description="Open bot")
    agent.run()  # Anyone can access

Example (with API key - opt-in):
    from a2a_lite.auth import APIKeyAuth

    agent = Agent(
        name="SecureBot",
        auth=APIKeyAuth(keys=["secret-key-123"]),
    )

Example (with OAuth2 - opt-in):
    from a2a_lite.auth import OAuth2Auth

    agent = Agent(
        name="EnterpriseBot",
        auth=OAuth2Auth(
            issuer="https://auth.company.com",
            audience="my-agent",
        ),
    )
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set
import hashlib
import hmac
import time


class AuthProvider(ABC):
    """Base class for authentication providers."""

    @abstractmethod
    async def authenticate(self, request: "AuthRequest") -> "AuthResult":
        """Authenticate a request."""
        pass

    @abstractmethod
    def get_scheme(self) -> Dict[str, Any]:
        """Get A2A security scheme for agent card."""
        pass


@dataclass
class AuthRequest:
    """Incoming authentication request."""
    headers: Dict[str, str]
    query_params: Dict[str, str] = field(default_factory=dict)
    body: Optional[bytes] = None
    method: str = "POST"
    path: str = "/"

    def get_header(self, name: str) -> Optional[str]:
        """Get a header value (case-insensitive)."""
        # Try exact match first, then case-insensitive
        if name in self.headers:
            return self.headers[name]
        lower = name.lower()
        for k, v in self.headers.items():
            if k.lower() == lower:
                return v
        return None


@dataclass
class AuthResult:
    """Authentication result."""
    authenticated: bool
    user_id: Optional[str] = None
    scopes: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @classmethod
    def success(
        cls,
        user_id: str,
        scopes: Optional[Set[str]] = None,
        **metadata,
    ) -> "AuthResult":
        return cls(
            authenticated=True,
            user_id=user_id,
            scopes=scopes or set(),
            metadata=metadata,
        )

    @classmethod
    def failure(cls, error: str) -> "AuthResult":
        return cls(authenticated=False, error=error)


class NoAuth(AuthProvider):
    """No authentication (default)."""

    async def authenticate(self, request: AuthRequest) -> AuthResult:
        return AuthResult.success(user_id="anonymous")

    def get_scheme(self) -> Dict[str, Any]:
        return {}


class APIKeyAuth(AuthProvider):
    """
    Simple API key authentication.

    Example:
        auth = APIKeyAuth(
            keys=["key1", "key2"],
            header="X-API-Key",  # or use query param
        )
    """

    def __init__(
        self,
        keys: List[str],
        header: str = "X-API-Key",
        query_param: Optional[str] = None,
    ):
        # Store only hashes of keys for security
        self._key_hashes = {
            hashlib.sha256(k.encode()).hexdigest() for k in keys
        }
        self.header = header
        self.query_param = query_param

    def _hash_key(self, key: str) -> str:
        """Hash a key using SHA-256."""
        return hashlib.sha256(key.encode()).hexdigest()

    async def authenticate(self, request: AuthRequest) -> AuthResult:
        # Check header (case-insensitive)
        key = request.get_header(self.header)

        # Check query param
        if not key and self.query_param:
            key = request.query_params.get(self.query_param)

        if not key:
            return AuthResult.failure("API key required")

        key_hash = self._hash_key(key)
        if key_hash not in self._key_hashes:
            return AuthResult.failure("Invalid API key")

        # Use hash prefix as user ID
        user_id = key_hash[:16]
        return AuthResult.success(user_id=user_id)

    def get_scheme(self) -> Dict[str, Any]:
        return {
            "type": "apiKey",
            "in": "header" if not self.query_param else "query",
            "name": self.header if not self.query_param else self.query_param,
        }


class BearerAuth(AuthProvider):
    """
    Bearer token authentication.

    For custom token validation (JWT, etc).

    Example:
        def validate_token(token: str) -> Optional[str]:
            # Your validation logic
            if is_valid(token):
                return get_user_id(token)
            return None

        auth = BearerAuth(validator=validate_token)
    """

    def __init__(
        self,
        validator: Callable[[str], Optional[str]],
        header: str = "Authorization",
    ):
        self.validator = validator
        self.header = header

    async def authenticate(self, request: AuthRequest) -> AuthResult:
        auth_header = request.get_header(self.header) or ""

        if not auth_header.startswith("Bearer "):
            return AuthResult.failure("Bearer token required")

        token = auth_header[7:]  # Remove "Bearer "

        user_id = self.validator(token)
        if user_id is None:
            return AuthResult.failure("Invalid token")

        return AuthResult.success(user_id=user_id)

    def get_scheme(self) -> Dict[str, Any]:
        return {
            "type": "http",
            "scheme": "bearer",
        }


class OAuth2Auth(AuthProvider):
    """
    OAuth2/OIDC authentication.

    Validates JWT tokens from an OAuth2 provider.

    Example:
        auth = OAuth2Auth(
            issuer="https://auth.company.com",
            audience="my-agent",
        )

    Requires: pip install a2a-lite[oauth]
    """

    def __init__(
        self,
        issuer: str,
        audience: str,
        jwks_uri: Optional[str] = None,
        algorithms: List[str] = None,
    ):
        self.issuer = issuer
        self.audience = audience
        self.jwks_uri = jwks_uri or f"{issuer}/.well-known/jwks.json"
        self.algorithms = algorithms or ["RS256"]
        self._jwks_client = None

    async def authenticate(self, request: AuthRequest) -> AuthResult:
        auth_header = request.get_header("Authorization") or ""

        if not auth_header.startswith("Bearer "):
            return AuthResult.failure("Bearer token required")

        token = auth_header[7:]

        try:
            import jwt
            from jwt import PyJWKClient

            # Get JWKS client (cached)
            if self._jwks_client is None:
                self._jwks_client = PyJWKClient(self.jwks_uri)

            # Get signing key
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)

            # Decode and validate
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=self.algorithms,
                audience=self.audience,
                issuer=self.issuer,
            )

            user_id = payload.get("sub", payload.get("email", "unknown"))
            scopes = set(payload.get("scope", "").split())

            return AuthResult.success(
                user_id=user_id,
                scopes=scopes,
                claims=payload,
            )

        except ImportError:
            return AuthResult.failure(
                "OAuth2 requires pyjwt: pip install a2a-lite[oauth]"
            )
        except Exception as e:
            return AuthResult.failure(f"Token validation failed: {str(e)}")

    def get_scheme(self) -> Dict[str, Any]:
        return {
            "type": "oauth2",
            "flows": {
                "authorizationCode": {
                    "authorizationUrl": f"{self.issuer}/authorize",
                    "tokenUrl": f"{self.issuer}/oauth/token",
                    "scopes": {},
                }
            },
        }


class CompositeAuth(AuthProvider):
    """
    Try multiple auth providers (first success wins).

    Example:
        auth = CompositeAuth([
            APIKeyAuth(keys=["admin-key"]),
            OAuth2Auth(issuer="..."),
        ])
    """

    def __init__(self, providers: List[AuthProvider]):
        self.providers = providers

    async def authenticate(self, request: AuthRequest) -> AuthResult:
        errors = []

        for provider in self.providers:
            result = await provider.authenticate(request)
            if result.authenticated:
                return result
            if result.error:
                errors.append(result.error)

        return AuthResult.failure("; ".join(errors) or "Authentication failed")

    def get_scheme(self) -> Dict[str, Any]:
        # Return first provider's scheme
        if self.providers:
            return self.providers[0].get_scheme()
        return {}


# Auth middleware helper
def require_auth(scopes: Optional[List[str]] = None):
    """
    Decorator to require authentication for a skill.

    Example:
        @agent.skill("admin_action")
        @require_auth(scopes=["admin"])
        async def admin_action(data: str, auth: AuthResult) -> str:
            return f"Admin {auth.user_id} did something"
    """
    required_scopes = set(scopes or [])

    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, auth: AuthResult = None, **kwargs):
            if auth is None or not auth.authenticated:
                return {"error": "Authentication required"}

            if required_scopes and not required_scopes.issubset(auth.scopes):
                return {
                    "error": "Insufficient permissions",
                    "required": list(required_scopes),
                    "provided": list(auth.scopes),
                }

            return await func(*args, auth=auth, **kwargs)

        wrapper.__wrapped__ = func
        wrapper.__requires_auth__ = True
        wrapper.__required_scopes__ = required_scopes
        return wrapper

    return decorator
