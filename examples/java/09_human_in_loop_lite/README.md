# Human-in-the-Loop Agent - A2A Lite (Java)

HITL workflow demonstration using the **real A2A Lite library**.

## Features

- Multi-step workflows with state management
- Confirmation dialogs
- Text input collection
- Multiple choice selection

## Skills

- `purchase` - Purchase with confirmation
- `delete_data` - Delete data with reason collection
- `approve_document` - Document approval workflow

## Running

```bash
./gradlew run
```

## Workflow Example

### 1. Initiate purchase
```bash
curl -X POST http://localhost:8795/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "SendMessage",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "m1",
        "parts": [{"text": "{\"skill\": \"purchase\", \"params\": {\"item\": \"Laptop\", \"amount\": 999.99}}"}]
      }
    }
  }'
```

Response includes `task_id` and asks for confirmation.

### 2. Confirm purchase
```bash
curl -X POST http://localhost:8795/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "id": "2",
    "method": "SendMessage",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "m1",
        "parts": [{"text": "{\"skill\": \"purchase\", \"params\": {\"task_id\": \"<TASK_ID>\", \"confirmation\": \"true\"}}"}]
      }
    }
  }'
```
