# Calculator Agent - Google A2A SDK (Python)

> **Multi-skill calculator agent using Google's official A2A Python SDK.**

This example demonstrates a complete, production-ready calculator agent with 5 arithmetic skills using the official Google A2A SDK. It shows how to properly implement:

- **AgentCard** with multiple skills (add, subtract, multiply, divide, power)
- **Custom AgentExecutor** with `execute()` and `cancel()` methods
- **TaskStore** (InMemoryTaskStore) for task persistence
- **DefaultRequestHandler** for handling A2A protocol requests
- **Starlette** app with agent card, JSON-RPC and REST routes (`create_agent_card_routes`, `create_jsonrpc_routes`, `create_rest_routes`)

---

## 📁 Files Overview

| File | Purpose | Lines |
|------|---------|-------|
| `main.py` | Complete server with AgentExecutor implementation | ~350 |
| `requirements.txt` | Dependencies including a2a-sdk[http-server] | ~10 |
| `README.md` | This documentation | ~200 |
| `agent_card.json` | Static agent card (for reference) | ~112 |
| `skills.py` | Calculator logic (reference) | ~150 |
| `test_calculator.py` | Integration tests | ~127 |

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd a2a-lite/examples/python/02_calculator_google
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run the Server

```bash
python main.py
```

The server will start at `http://localhost:8788`

---

## 🧪 Testing

### Get Agent Card

```bash
curl http://localhost:8788/.well-known/agent-card.json
```

### Test Addition

```bash
curl -X POST http://localhost:8788/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendMessage",
    "id": "1",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "parts": [{"text": "{\"skill\": \"add\", \"params\": {\"a\": 10, \"b\": 5}}"}],
        "messageId": "msg-1"
      }
    }
  }'
```

**Expected response:** Result of 15

### Test Division

```bash
curl -X POST http://localhost:8788/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendMessage",
    "id": "2",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "parts": [{"text": "{\"skill\": \"divide\", \"params\": {\"a\": 10, \"b\": 3}}"}],
        "messageId": "msg-2"
      }
    }
  }'
```

**Expected response:** Result of 3.333... with remainder 1

### Test Division by Zero (Error Handling)

```bash
curl -X POST http://localhost:8788/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendMessage",
    "id": "3",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "parts": [{"text": "{\"skill\": \"divide\", \"params\": {\"a\": 10, \"b\": 0}}"}],
        "messageId": "msg-3"
      }
    }
  }'
```

**Expected response:** Error indicating division by zero

### Test Power

```bash
curl -X POST http://localhost:8788/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendMessage",
    "id": "4",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "parts": [{"text": "{\"skill\": \"power\", \"params\": {\"base\": 2, \"exponent\": 10}}"}],
        "messageId": "msg-4"
      }
    }
  }'
```

**Expected response:** Result of 1024

### Run Integration Tests

```bash
python -m pytest test_calculator.py -v
```

---

## 📖 Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│              Starlette (agent card + JSON-RPC + REST routes)     │
│                         (main.py:300)                           │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DefaultRequestHandler                         │
│              (handles A2A protocol methods)                     │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
            ┌──────────────┐    ┌──────────────┐
            │CalculatorExecutor│  │ InMemoryTaskStore │
            │  (execute()  │    │              │
            │   cancel())  │    │              │
            └──────────────┘    └──────────────┘
```

### Key Components

#### 1. AgentCard

```python
AGENT_CARD = AgentCard(
    name="CalculatorAgent",
    description="A calculator agent with arithmetic operations",
    supported_interfaces=[
        AgentInterface(
            url="http://localhost:8788/",
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        ),
    ],
    capabilities=AgentCapabilities(streaming=True, push_notifications=False),
    skills=[
        AgentSkill(id="add", name="Addition", ...),
        AgentSkill(id="subtract", name="Subtraction", ...),
        AgentSkill(id="multiply", name="Multiplication", ...),
        AgentSkill(id="divide", name="Division", ...),
        AgentSkill(id="power", name="Power", ...),
    ],
)
```

#### 2. CalculatorExecutor

```python
class CalculatorExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Parse request, execute skill, send events
        ...
    
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Handle cancellation request
        ...
```

#### 3. Server Setup

```python
from starlette.applications import Starlette
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes, create_rest_routes
from a2a.server.tasks import InMemoryTaskStore

agent_executor = CalculatorExecutor()
handler = DefaultRequestHandler(agent_executor, InMemoryTaskStore(), AGENT_CARD)
app = Starlette(
    routes=create_agent_card_routes(AGENT_CARD)
    + create_jsonrpc_routes(handler, rpc_url="/")
    + create_rest_routes(handler)
)
```

---

## 🔌 Available Skills

| Skill ID | Parameters | Returns | Description |
|----------|------------|---------|-------------|
| `add` | `a`, `b` | `result` | Add two numbers |
| `subtract` | `a`, `b` | `result` | Subtract b from a |
| `multiply` | `a`, `b` | `result` | Multiply two numbers |
| `divide` | `a`, `b` | `result`, `remainder` | Divide a by b |
| `power` | `base`, `exponent` | `result` | Raise base to exponent |

---

## 📡 A2A Protocol Methods

The server implements the following A2A JSON-RPC methods:

| Method | Description |
|--------|-------------|
| `SendMessage` | Send a message and wait for response |
| `GetTask` | Get task status |
| `CancelTask` | Cancel a running task |
| `SendStreamingMessage` | Send a message with streaming response |

---

## 🔧 Request Format

```json
{
  "jsonrpc": "2.0",
  "method": "SendMessage",
  "id": "unique-request-id",
  "params": {
    "message": {
      "role": "ROLE_USER",
      "parts": [{
        "text": "{\"skill\": \"add\", \"params\": {\"a\": 10, \"b\": 5}}"
      }],
      "messageId": "unique-message-id"
    }
  }
}
```

All JSON-RPC requests must include the `A2A-Version: 1.0` HTTP header.

---

## 📊 Comparison: Google SDK vs A2A Lite

| Feature | Google SDK (this example) | A2A Lite |
|---------|---------------------------|----------|
| Lines of Code | ~350 | ~40 |
| Files | 1 main file | 1 file |
| Abstraction Level | Full SDK | Lightweight wrapper |
| Task Management | TaskStore | Built-in |
| Protocol Compliance | Full A2A protocol | Simplified |
| Extensibility | High (full SDK) | Medium |

---

## 📚 References

- [Google A2A Python SDK Documentation](https://github.com/google/A2A/tree/main/samples/python)
- [A2A Protocol Specification](https://google.github.io/A2A/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

---

## 📝 License

This example is provided as-is for educational purposes.
