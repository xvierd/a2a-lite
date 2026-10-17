# Authentication - A2A Lite (Python)

> **Secure agent with authentication - simplified with A2A Lite.**

This example demonstrates how A2A Lite simplifies authentication implementation while maintaining the same security features as the Google SDK approach.

---

## 📋 Complexity Level: **MEDIUM** (but much simpler!)

**Concepts Covered:**
- API Key authentication (one-liner)
- Bearer token validation
- Role-based access control
- Auth context injection

---

## 📁 Files Overview

| File | Purpose | Lines |
|------|---------|-------|
| `agent.py` | Complete secure agent | ~60 |
| `requirements.txt` | Dependencies | ~2 |
| `test_secure.py` | Unit tests | ~30 |

**Total: ~92 lines across 3 files**

Compare to Google SDK: **~374 lines → 75% reduction!**

---

## 🚀 Quick Start

```bash
# From the repository root:
cd examples/python/05_auth_lite
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python agent.py
```

---

## 🧪 Testing Authentication

### Test 1: Without Auth (Fails)

```bash
curl -X POST http://localhost:8790/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{"jsonrpc": "2.0", "method": "SendMessage", "id": "1", "params": {"message": {"messageId": "msg-1", "role": "ROLE_USER", "parts": [{"text": "{\"skill\": \"get_secret\"}"}]}}}'

# Expected: 401 Unauthorized
```

### Test 2: With API Key (Succeeds)

```bash
curl -X POST http://localhost:8790/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -H "X-API-Key: secret-key-123" \
  -d '{"jsonrpc": "2.0", "method": "SendMessage", "id": "1", "params": {"message": {"messageId": "msg-2", "role": "ROLE_USER", "parts": [{"text": "{\"skill\": \"get_secret\"}"}]}}}'

# Expected: {"secret": "The answer is 42"}
```

### Test 3: Access Auth Info in Skill

```bash
curl -X POST http://localhost:8790/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -H "Authorization: Bearer valid-token-abc" \
  -d '{"jsonrpc": "2.0", "method": "SendMessage", "id": "1", "params": {"message": {"messageId": "msg-3", "role": "ROLE_USER", "parts": [{"text": "{\"skill\": \"whoami\"}"}]}}}'

# Parsed result: {"identity": "bearer_user_1", "scopes": [], "authenticated": true}
```

---

## 📖 Code Comparison

### Google SDK Approach

```python
# auth.py - ~200 lines
class APIKeyAuth(AuthProvider):
    def __init__(self, keys):
        self._hashed_keys = {hashlib.sha256(k.encode()).hexdigest() for k in keys}
    
    def authenticate(self, headers, query_params):
        api_key = headers.get("x-api-key")
        if api_key:
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            if key_hash in self._hashed_keys:
                return AuthContext(scheme="apiKey", identity="...")
        return None

# main.py - Manual middleware
@app.post("/")
async def handle(request):
    auth = auth_middleware.authenticate(request)
    if not auth:
        return JSONResponse({"error": "Unauthorized"}, 401)
    # ... process request
```

### A2A Lite Approach

```python
from a2a_lite import Agent, APIKeyAuth, BearerAuth
from a2a_lite.auth import AuthResult

agent = Agent(
    name="SecureAgent",
    description="Authenticated skills",
    auth=APIKeyAuth(keys=["secret-key-123"])  # One line!
)

@agent.skill("whoami")
async def whoami(auth: AuthResult) -> dict:
    return {"user": auth.user_id, "scopes": sorted(auth.scopes)}
```

---

## 🔐 Authentication Behavior

| Feature | A2A Lite Implementation |
|---------|------------------------|
| **Key Hashing** | SHA-256 automatic |
| **Stable Identity** | `APIKeyAuth(principals={key: user_id})` preserves ownership during key rotation |
| **Multiple Schemes** | `APIKeyAuth`, `BearerAuth`, `CompositeAuth` |
| **Context Injection** | Type-hint `auth: AuthResult` |
| **Error Handling** | Invalid HTTP credentials return 401; skill permission failures use protocol errors |

Configured authentication protects every protocol operation, including the demo's `public_info` skill. Omitting an `AuthResult` parameter does not make a skill public. Agent-card discovery remains public. These hardcoded credentials are for local demonstrations; see the [deployment guide](../../../packages/python/docs/production.md) for namespaces, tenant authorization and durable profiles.

---

## 🎯 Progressive Complexity

### Level 1: Basic API Key

```python
from a2a_lite import Agent, APIKeyAuth

agent = Agent(
    name="SecureAgent",
    description="API key protected skills",
    auth=APIKeyAuth(keys=["secret-key"])
)
```

### Level 2: Bearer Tokens

```python
from a2a_lite.auth import BearerAuth

demo_tokens = {"example-token": "alice"}
agent = Agent(
    name="BearerAgent",
    description="Opaque bearer token demonstration",
    auth=BearerAuth(validator=demo_tokens.get),
)
```

The validator returns a stable user ID or `None`. For signed JWTs, use `OAuth2Auth(issuer=..., audience=...)` with the `[oauth]` extra.

### Level 3: Multiple Schemes

```python
from a2a_lite.auth import CompositeAuth

agent = Agent(
    name="MultipleSchemes",
    description="API key or bearer authentication",
    auth=CompositeAuth([
        APIKeyAuth(keys=["key1"]),
        BearerAuth(validator=demo_tokens.get)
    ])
)
```

### Level 4: Access Auth in Skills

```python
from a2a_lite.auth import AuthResult

@agent.skill("profile")
async def get_profile(auth: AuthResult) -> dict:
    return {"user": auth.user_id, "scopes": sorted(auth.scopes)}
```

---

## 📊 Comparison Summary

| Aspect | Google SDK | A2A Lite |
|--------|------------|----------|
| **Lines** | ~374 | ~92 |
| **Files** | 5 | 3 |
| **Auth Setup** | Custom classes | One-line |
| **Context Access** | Manual passing | Type-hint injection |
| **Error Handling** | Manual | Automatic |

See [Google SDK version](../05_auth_google/) for full comparison.
