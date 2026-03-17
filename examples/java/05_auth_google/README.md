# Google A2A SDK - Authentication Example

Complete authentication example using the official Google A2A Java SDK approach.

## Features

- **API Key Authentication**: Header (`X-API-Key`) and Query parameter (`api_key`) support
- **Bearer Token Authentication**: JWT-style Bearer tokens via `Authorization` header
- **SecurityScheme Configuration**: Full A2A specification-compliant security schemes
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
    ├── SecureAgentServer.java          # Main server (~150 lines)
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
```

## Test API

### 1. Get Agent Card (shows security schemes)
```bash
curl http://localhost:8080/.well-known/agent.json
```

### 2. Get Secret - API Key in Header
```bash
curl -X POST http://localhost:8080/skills/get_secret \
  -H "X-API-Key: ak_user_12345"
```

### 3. Get Secret - API Key in Query
```bash
curl -X POST "http://localhost:8080/skills/get_secret?api_key=ak_user_12345"
```

### 4. Get Secret - Bearer Token
```bash
curl -X POST http://localhost:8080/skills/get_secret \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.user"
```

### 5. Get User Info - USER role
```bash
curl -X POST http://localhost:8080/skills/get_user_info \
  -H "X-API-Key: ak_user_12345"
```

### 6. Admin Only - ADMIN role (success)
```bash
curl -X POST http://localhost:8080/skills/admin_only \
  -H "X-API-Key: ak_admin_67890" \
  -H "Content-Type: application/json" \
  -d '{"operation":"status"}'
```

### 7. Admin Only - USER role (failure - 403)
```bash
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
| SecureAgentServer.java | 236 lines |
| Security classes (3) | 351 lines |
| Skill classes (3) | 316 lines |
| Model classes (3) | 60 lines |
| **Total** | **963 lines** |
