# Authentication Example — A2A protocol v1.0 from scratch (Java)

Complete authentication example implementing the **A2A v1.0 wire protocol by hand**
with Javalin + Jackson — **no SDK**. For the official Java SDK approach see
`packages/java` (LiteAgentExecutor / Quarkus integration).

## Features

- **API Key Authentication**: Header (`X-API-Key`) and Query parameter (`api_key`) support
- **Bearer Token Authentication**: JWT-style Bearer tokens via `Authorization` header
- **SecurityScheme Configuration**: A2A v1.0 agent card with `securitySchemes` + `securityRequirements`
- **Role-Based Access Control (RBAC)**: USER, ADMIN, GUEST, SERVICE roles
- **Protected Skills**:
  - `get_secret` - Any authenticated user
  - `get_user_info` - USER or ADMIN role required
  - `admin_only` - ADMIN role only

## Project Structure

```
05_auth_google/
├── pom.xml
├── README.md
└── src/main/java/com/example/auth/
    ├── SecureAgentServer.java          # Main server (A2A v1.0 wire, no SDK)
    ├── model/
    │   ├── SecretResponse.java         # Response DTO
    │   ├── UserInfo.java               # User info DTO
    │   └── AdminResponse.java          # Admin response DTO
    ├── security/
    │   ├── ApiKeyAuthenticator.java    # API key auth logic
    │   ├── BearerTokenAuthenticator.java # Bearer token auth
    │   └── SecuritySchemes.java        # Security scheme definitions
    └── skills/
        ├── GetSecretSkill.java         # Secret skill with auth
        ├── GetUserInfoSkill.java       # User info with RBAC
        └── AdminOnlySkill.java         # Admin-only skill
```

## Build & Run

```bash
# Compile
mvn clean package

# Run
java -jar target/05-auth-google-1.0.0.jar
# or
mvn exec:java
```

## Wire protocol (A2A v1.0)

- Agent card: `GET /.well-known/agent-card.json` (with `supportedInterfaces`, `securitySchemes`, `securityRequirements`)
- JSON-RPC method: `SendMessage` on `POST /`
- Every RPC response carries the `A2A-Version: 1.0` header
- Messages use `ROLE_USER` / `ROLE_AGENT` and text parts `{"text": "..."}` (no `kind`/`type`)
- The skill call travels inside the text part as JSON: `{"skill": "<name>", "params": {...}}`
- Responses: `{"result": {"message": {"messageId": "<uuid>", "role": "ROLE_AGENT", "parts": [{"text": "..."}]}}}`

## Test API

### 1. Get Agent Card (v1.0, shows security schemes)
```bash
curl http://localhost:8080/.well-known/agent-card.json
```

### 2. SendMessage (get_secret) - API Key in Header
```bash
curl -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -H "X-API-Key: ak_user_12345" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "SendMessage",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "m1",
        "parts": [{"text": "{\"skill\": \"get_secret\", \"params\": {}}"}]
      }
    }
  }'
```

### 3. SendMessage (get_secret) - Bearer Token
```bash
curl -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.user" \
  -d '{
    "jsonrpc": "2.0",
    "id": "2",
    "method": "SendMessage",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "m2",
        "parts": [{"text": "{\"skill\": \"get_secret\", \"params\": {}}"}]
      }
    }
  }'
```

### 4. SendMessage (admin_only) - ADMIN role
```bash
curl -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -H "X-API-Key: ak_admin_67890" \
  -d '{
    "jsonrpc": "2.0",
    "id": "3",
    "method": "SendMessage",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "m3",
        "parts": [{"text": "{\"skill\": \"admin_only\", \"params\": {\"operation\": \"status\"}}"}]
      }
    }
  }'
```

### 5. Unauthenticated request (401 JSON-RPC error)
```bash
curl -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"4","method":"SendMessage","params":{"message":{"role":"ROLE_USER","messageId":"m4","parts":[{"text":"{\"skill\":\"get_secret\"}"}]}}}'
```

## Direct REST skill endpoints (convenience, outside the A2A wire)

The server also exposes plain REST endpoints for each skill:

```bash
# API Key in header
curl -X POST http://localhost:8080/skills/get_secret -H "X-API-Key: ak_user_12345"

# API Key in query
curl -X POST "http://localhost:8080/skills/get_secret?api_key=ak_user_12345"

# Bearer token
curl -X POST http://localhost:8080/skills/get_secret \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.user"

# Admin only (success)
curl -X POST http://localhost:8080/skills/admin_only \
  -H "X-API-Key: ak_admin_67890" \
  -H "Content-Type: application/json" \
  -d '{"operation":"status"}'

# Admin only with USER role (403)
curl -X POST http://localhost:8080/skills/admin_only \
  -H "X-API-Key: ak_user_12345" \
  -H "Content-Type: application/json" \
  -d '{"operation":"status"}'
```

## Demo Credentials

| API Key | Username | Roles |
|---------|----------|-------|
| `ak_user_12345` | user1 | USER |
| `ak_admin_67890` | admin1 | ADMIN, USER |
| `ak_guest_abcde` | guest1 | GUEST |

| Bearer Token | Username | Roles |
|--------------|----------|-------|
| `eyJhbGciOiJIUzI1NiJ9.user` | john_doe | USER |
| `eyJhbGciOiJIUzI1NiJ9.admin` | jane_admin | ADMIN, USER |
| `eyJhbGciOiJIUzI1NiJ9.service` | service_account | SERVICE |

## Code Statistics

| Component | Lines of Code |
|-----------|--------------|
| SecureAgentServer.java | ~400 lines |
| Security classes (3) | 351 lines |
| Skill classes (3) | 316 lines |
| Model classes (3) | 60 lines |
