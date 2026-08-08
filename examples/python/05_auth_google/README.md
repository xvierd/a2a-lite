# Authentication - Google A2A SDK (Python)

> **Secure agent with API Key and Bearer token authentication using the REAL Google A2A SDK.**

This example demonstrates how to implement authentication in A2A agents using the official Google A2A SDK (`a2a-sdk[http-server]`). It covers API Key validation, Bearer token verification, role-based access control, and proper integration with the SDK's authentication system.

---

## 📋 Complexity Level: **MEDIUM**

**Concepts Covered:**
- API Key authentication (header & query param)
- Bearer token authentication
- Security scheme configuration with SDK types
- Starlette authentication backend integration
- Custom ServerCallContextBuilder for auth
- Protected skills with role-based access control
- Authentication errors in task status

---

## 📁 Files Overview

| File | Purpose | Lines |
|------|---------|-------|
| `main.py` | Complete server with SDK integration | ~470 |
| `auth.py` | Authentication backend and helpers | ~240 |
| `skills.py` | Protected skill implementations | ~200 |
| `requirements.txt` | SDK dependencies | ~5 |

**Total: ~900 lines across 4 files**

---

## 🚀 Quick Start

```bash
cd python/05_auth_google
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run the agent
python main.py
```

The server will start on `http://localhost:8790`

---

## 🧪 Testing Authentication

### Important: SDK Wire Format

The A2A SDK uses **Protobuf** for wire format. The JSON structure differs from the Pydantic models:

| Field | Pydantic Model | Protobuf JSON |
|-------|---------------|---------------|
| Message field | `message` | `request` |
| Content field | `parts` | `content` (array) |
| Role enum | `"user"`, `"agent"` | `"ROLE_USER"`, `"ROLE_AGENT"` |

### Test 1: Get Agent Card (Public)

```bash
curl http://localhost:8790/.well-known/agent-card.json | python -m json.tool
```

**Expected:** Agent card with security schemes defined.

### Test 2: Request Without Auth

```bash
curl -X POST http://localhost:8790/message:send \
  -H "Content-Type: application/json" \
  -d '{
    "request": {
      "messageId": "msg-1",
      "role": "ROLE_USER",
      "content": [{"text": "get_secret"}]
    }
  }'
```

**Expected:** Task status with `TASK_STATE_AUTH_REQUIRED` state.

### Test 3: API Key Authentication (Header)

```bash
curl -X POST http://localhost:8790/message:send \
  -H "Content-Type: application/json" \
  -H "X-API-Key: secret-key-123" \
  -d '{
    "request": {
      "messageId": "msg-1",
      "role": "ROLE_USER",
      "content": [{"text": "get_secret"}]
    }
  }'
```

**Expected:** Task completed with secret data artifact.

### Test 4: Bearer Token Authentication

```bash
curl -X POST http://localhost:8790/message:send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer valid-token-abc" \
  -d '{
    "request": {
      "messageId": "msg-1",
      "role": "ROLE_USER",
      "content": [{"text": "get_user_info"}]
    }
  }'
```

**Expected:** User info including identity, scheme, and permissions.

### Test 5: Admin-only Skill (Without Admin Permission)

```bash
curl -X POST http://localhost:8790/message:send \
  -H "Content-Type: application/json" \
  -H "X-API-Key: secret-key-123" \
  -d '{
    "request": {
      "messageId": "msg-1",
      "role": "ROLE_USER",
      "content": [{"text": "admin_only"}]
    }
  }'
```

**Expected:** Task `TASK_STATE_REJECTED` - requires admin permission.

### Test 6: Admin-only Skill (With Admin Permission)

```bash
curl -X POST http://localhost:8790/message:send \
  -H "Content-Type: application/json" \
  -H "X-API-Key: admin-key-789" \
  -d '{
    "request": {
      "messageId": "msg-1",
      "role": "ROLE_USER",
      "content": [{"text": "admin_only"}]
    }
  }'
```

**Expected:** Admin data with system status and metrics.

### Test 7: API Key in Query Parameter

```bash
curl -X POST "http://localhost:8790/message:send?api_key=secret-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "request": {
      "messageId": "msg-1",
      "role": "ROLE_USER",
      "content": [{"text": "get_secret"}]
    }
  }'
```

**Expected:** Task completed with secret data.

---

## 📖 Key Concepts

### 1. AgentCard with Security Schemes (SDK Types)

```python
from a2a.types import AgentCard, AgentInterface, APIKeySecurityScheme, HTTPAuthSecurityScheme

AGENT_CARD = AgentCard(
    name="SecureAgent",
    description="A secure agent requiring authentication",
    version="1.0.0",
    supported_interfaces=[
        AgentInterface(
            url="http://localhost:8790/",
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        ),
    ],
    skills=[...],
    security_schemes={
        "apiKeyAuth": APIKeySecurityScheme(
            type="apiKey",
            in_="header",
            name="X-API-Key",
            description="API Key authentication",
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
```

### 2. Starlette Authentication Backend

```python
from starlette.authentication import AuthenticationBackend, AuthCredentials
from a2a.server.context import User

class A2AAuthBackend(AuthenticationBackend):
    async def authenticate(self, conn):
        # Check API Key in header
        api_key = conn.headers.get("X-API-Key")
        if api_key and api_key in VALID_KEYS:
            return AuthCredentials(["read"]), AuthenticatedUser(...)
        
        # Check Bearer token
        auth_header = conn.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if token in VALID_TOKENS:
                return AuthCredentials(["read", "write"]), AuthenticatedUser(...)
        
        return None  # Not authenticated
```

### 3. Custom ServerCallContextBuilder

```python
from a2a.server.routes.common import DefaultServerCallContextBuilder

class AuthCallContextBuilder(DefaultServerCallContextBuilder):
    def build(self, request) -> ServerCallContext:
        context = super().build(request)
        
        # Add auth info to state if user is authenticated
        if context.user.is_authenticated:
            context.state['auth'] = {
                'identity': context.user.user_name,
                'permissions': getattr(context.user, 'permissions', []),
                'scheme': getattr(context.user, 'scheme', 'unknown'),
            }
        
        return context
```

### 4. Protected Skills with RequestContext

```python
from a2a.server.agent_execution import RequestContext

def get_secret(context: RequestContext) -> dict:
    """Get secret data - requires authentication."""
    auth = get_auth_context(context)
    if not auth:
        raise AuthenticationError("Authentication required")
    
    return {
        "secret": "The answer is 42",
        "accessed_by": auth['identity'],
    }
```

### 5. Agent Executor with Auth Check

```python
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue

class SecureAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Get authentication from context
        auth_context = get_auth_context(context)
        
        try:
            # Execute skill with auth check
            result = execute_skill(skill_name, context)
            
            # Send success response
            await event_queue.enqueue_event(Artifact(...))
            await event_queue.enqueue_event(
                TaskStatus(state=TaskState.TASK_STATE_COMPLETED, ...)
            )
        
        except AuthenticationError:
            await event_queue.enqueue_event(
                TaskStatus(state=TaskState.TASK_STATE_AUTH_REQUIRED, ...)
            )
        except AuthorizationError:
            await event_queue.enqueue_event(
                TaskStatus(state=TaskState.TASK_STATE_REJECTED, ...)
            )
```

### 6. Building the Application

```python
from starlette.applications import Starlette
from starlette.middleware.authentication import AuthenticationMiddleware
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes, create_rest_routes
from a2a.server.tasks import InMemoryTaskStore

# Create SDK components
agent_executor = SecureAgentExecutor()
handler = DefaultRequestHandler(
    agent_executor=agent_executor,
    task_store=InMemoryTaskStore(),
    agent_card=AGENT_CARD,
)

# The auth-aware context builder validates credentials per request
context_builder = AuthCallContextBuilder()

# Build Starlette app with agent card, JSON-RPC and REST routes
app = Starlette(
    routes=(
        create_agent_card_routes(AGENT_CARD)
        + create_jsonrpc_routes(handler, rpc_url="/", context_builder=context_builder)
        + create_rest_routes(handler, context_builder=context_builder)
    )
)

# Add Starlette auth middleware
app.add_middleware(AuthenticationMiddleware, backend=A2AAuthBackend())
```

---

## 🔐 Demo Credentials

| Type | Credential | Identity | Permissions |
|------|------------|----------|-------------|
| API Key | `secret-key-123` | api_user_1 | read |
| API Key | `client-key-456` | api_user_2 | read, write |
| API Key | `admin-key-789` | admin_user | read, write, admin |
| Bearer | `valid-token-abc` | bearer_user_1 | read, write |
| Bearer | `user-token-def` | bearer_user_2 | read |
| Bearer | `admin-token-ghi` | admin_user | read, write, admin |

---

## 🔐 Security Features

| Feature | Implementation |
|---------|----------------|
| **API Keys** | Header (`X-API-Key`) and Query param (`?api_key=`) |
| **Bearer Tokens** | `Authorization: Bearer <token>` |
| **SDK Integration** | Uses real `APIKeySecurityScheme` and `HTTPAuthSecurityScheme` |
| **User Type** | Custom `AuthenticatedUser` implementing SDK's `User` interface |
| **Auth Backend** | Starlette `AuthenticationBackend` for middleware integration |
| **Context Building** | Custom `ServerCallContextBuilder` for auth context propagation |
| **Skill Protection** | `get_auth_context()` and permission checks |
| **Error Handling** | SDK task states: `TASK_STATE_AUTH_REQUIRED`, `TASK_STATE_REJECTED`, `TASK_STATE_COMPLETED` |

---

## 📊 SDK Components Used

| Component | Purpose |
|-----------|---------|
| `AgentCard` | Agent definition with security schemes |
| `APIKeySecurityScheme` | API Key security scheme type |
| `HTTPAuthSecurityScheme` | Bearer token security scheme type |
| `AgentSkill` | Skill definitions |
| `create_agent_card_routes` / `create_jsonrpc_routes` / `create_rest_routes` | Route builders for the Starlette app |
| `AgentExecutor` | Core agent logic execution |
| `RequestContext` | Request context with auth info |
| `ServerCallContext` | Server call context with user and state |
| `DefaultRequestHandler` | HTTP request handler |
| `InMemoryTaskStore` | Task storage |
| `EventQueue` | Async event queue for responses |
| `TaskStatus` / `TaskState` | Task status updates |
| `Artifact` / `new_text_part` | Response artifacts |

---

## ⚠️ Security Notes

> **Demo Only**: Credentials are hardcoded for demonstration. In production:
> - Use environment variables or secure vaults (HashiCorp Vault, AWS Secrets Manager)
> - Implement proper key rotation
> - Use HTTPS/TLS for all communications
> - Add rate limiting
> - Implement token expiration (JWT)
> - Audit logging for security events

---

## 🔗 A2A Specification Compliance

This implementation follows the [A2A Specification](https://github.com/google/A2A):

- ✅ AgentCard with `securitySchemes` and `security` fields
- ✅ Proper authentication state handling (`TASK_STATE_AUTH_REQUIRED`, `TASK_STATE_REJECTED`)
- ✅ Multiple authentication schemes (apiKey, bearer)
- ✅ User identity propagation through ServerCallContext
- ✅ Standard A2A endpoints (`/message:send`, `/.well-known/agent-card.json`)

---

## 📚 References

- [Google A2A Specification](https://github.com/google/A2A)
- [a2a-sdk Python Package](https://github.com/a2aproject/a2a-python)
- [Starlette Authentication](https://www.starlette.io/authentication/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
