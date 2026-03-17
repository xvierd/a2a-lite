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
cd python/05_auth_lite
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
  -d '{"jsonrpc": "2.0", "method": "message/send", "id": "1", "params": {"message": {"role": "user", "parts": [{"type": "text", "text": "{\"skill\": \"get_secret\"}"}]}}}'

# Expected: 401 Unauthorized
```

### Test 2: With API Key (Succeeds)

```bash
curl -X POST http://localhost:8790/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: secret-key-123" \
  -d '{"jsonrpc": "2.0", "method": "message/send", "id": "1", "params": {"message": {"role": "user", "parts": [{"type": "text", "text": "{\"skill\": \"get_secret\"}"}]}}}'

# Expected: {"secret": "The answer is 42"}
```

### Test 3: Access Auth Info in Skill

```bash
curl -X POST http://localhost:8790/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer valid-token-abc" \
  -d '{"jsonrpc": "2.0", "method": "message/send", "id": "1", "params": {"message": {"role": "user", "parts": [{"type": "text", "text": "{\"skill\": \"whoami\"}"}]}}}'

# Expected: {"user": "bearer_user_valid-t...", "scheme": "bearer"}
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
    auth=APIKeyAuth(keys=["secret-key-123"])  # One line!
)

@agent.skill("whoami")
async def whoami(auth: AuthResult) -> dict:
    return {"user": auth.identity, "scheme": auth.scheme}
```

---

## 🔐 Security Features (Same as Google SDK!)

| Feature | A2A Lite Implementation |
|---------|------------------------|
| **Key Hashing** | SHA-256 automatic |
| **Timing Safe** | Uses `hmac.compare_digest` |
| **Multiple Schemes** | `APIKeyAuth`, `BearerAuth`, `CompositeAuth` |
| **Context Injection** | Type-hint `auth: AuthResult` |
| **Error Handling** | Automatic 401/403 responses |

---

## 🎯 Progressive Complexity

### Level 1: Basic API Key

```python
from a2a_lite import Agent, APIKeyAuth

agent = Agent(
    name="SecureAgent",
    auth=APIKeyAuth(keys=["secret-key"])
)
```

### Level 2: Bearer Tokens

```python
from a2a_lite.auth import BearerAuth

agent = Agent(
    auth=BearerAuth(secret="jwt-secret")
)
```

### Level 3: Multiple Schemes

```python
from a2a_lite.auth import CompositeAuth

agent = Agent(
    auth=CompositeAuth([
        APIKeyAuth(keys=["key1"]),
        BearerAuth(secret="jwt-secret")
    ])
)
```

### Level 4: Access Auth in Skills

```python
from a2a_lite.auth import AuthResult

@agent.skill("profile")
async def get_profile(auth: AuthResult) -> dict:
    # auth.identity, auth.scheme, auth.permissions
    return {"user": auth.identity}
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
