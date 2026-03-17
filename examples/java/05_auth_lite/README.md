# Secure Agent - A2A Lite (Java)

Agent with **API Key authentication** using the real A2A Lite library.

## Features

- Uses `APIKeyAuth` from `com.a2alite.auth`
- Keys are stored as SHA-256 hashes for security
- Simple authentication setup with the builder pattern

## Running

```bash
./gradlew run
```

## API Usage

### Without authentication (401 error)
```bash
curl -X POST http://localhost:8791/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": "1", "method": "message/send", "params": {"message": {"parts": [{"type": "text", "text": "{\"skill\": \"get_secret\"}"}]}}}'
```

### With authentication
```bash
curl -X POST http://localhost:8791/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: secret-key-user-12345" \
  -d '{"jsonrpc": "2.0", "id": "1", "method": "message/send", "params": {"message": {"parts": [{"type": "text", "text": "{\"skill\": \"get_secret\"}"}]}}}'
```

## Valid API Keys

- `secret-key-user-12345`
- `secret-key-admin-67890`
