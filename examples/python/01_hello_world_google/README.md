# Hello World - Google A2A Python SDK (Official)

A complete working example using the official **a2a-sdk** Python package.

## 📦 Installation

### Using pip

```bash
pip install "a2a-sdk[http-server]"
```

### Using uv (recommended)

```bash
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install "a2a-sdk[http-server]"
```

## 🚀 Running the Agent

```bash
python main.py
```

The server will start on `http://localhost:8787`

## 🧪 Testing the Agent

### 1. Check Agent Card

```bash
curl http://localhost:8787/.well-known/agent-card.json
```

Expected response:
```json
{
  "name": "HelloAgent",
  "description": "A friendly greeting agent that responds to messages using Google A2A SDK",
  "version": "1.0.0",
  "supportedInterfaces": [
    {
      "url": "http://localhost:8787/",
      "protocolBinding": "JSONRPC",
      "protocolVersion": "1.0"
    },
    {
      "url": "http://localhost:8787/",
      "protocolBinding": "HTTP+JSON",
      "protocolVersion": "1.0"
    }
  ],
  "capabilities": {
    "streaming": false,
    "pushNotifications": false,
    "stateTransitionHistory": false
  },
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "skills": [
    {
      "id": "greet",
      "name": "Greeting",
      "description": "Responds with a friendly greeting message",
      "tags": ["greeting", "hello", "welcome"]
    }
  ]
}
```

### 2. Send a Message

```bash
curl -X POST http://localhost:8787/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "SendMessage",
    "params": {
      "message": {
        "messageId": "msg-1",
        "role": "ROLE_USER",
        "parts": [{"text": "Hello from A2A!"}]
      }
    }
  }'
```

Expected response:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "message": {
      "messageId": "msg-xxx",
      "role": "ROLE_AGENT",
      "parts": [{"text": "Hello! You said: 'Hello from A2A!'. Welcome to A2A! 👋"}]
    }
  }
}
```

### 3. Verify SDK Installation

```bash
python -c "from a2a.server.routes import create_jsonrpc_routes; print('✅ SDK OK')"
```

## 📚 API Reference

### Core Components

#### 1. AgentCard

```python
from a2a.types import AgentCard, AgentInterface, AgentSkill, AgentCapabilities

agent_card = AgentCard(
    name="HelloAgent",
    description="A friendly greeting agent",
    version="1.0.0",
    # v1.0: no top-level url; endpoints are declared per protocol binding
    supported_interfaces=[
        AgentInterface(
            url="http://localhost:8787/",
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        ),
    ],
    capabilities=AgentCapabilities(
        streaming=False,
        push_notifications=False,
    ),
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    skills=[
        AgentSkill(
            id="greet",
            name="Greeting",
            description="Responds with a greeting",
            tags=["greeting"],
        )
    ],
)
```

#### 2. AgentExecutor (Abstract Class)

```python
from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue

class MyAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Process the request and publish events
        pass
    
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Handle cancellation
        pass
```

#### 3. Infrastructure Components

```python
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.request_handlers import DefaultRequestHandler

# Create in-memory store
task_store = InMemoryTaskStore()

# Create request handler
handler = DefaultRequestHandler(
    agent_executor=agent_executor,
    task_store=task_store,
    agent_card=agent_card,
)
```

#### 4. Starlette Application

```python
from starlette.applications import Starlette
from a2a.server.routes import (
    create_agent_card_routes,
    create_jsonrpc_routes,
    create_rest_routes,
)

# v1.0: the 0.3 application builders were removed; the app is
# assembled from route factories on a plain Starlette app
app = Starlette(
    routes=create_agent_card_routes(agent_card)
    + create_jsonrpc_routes(handler, rpc_url="/")
    + create_rest_routes(handler)
)
```

## 📖 Resources

- **PyPI**: https://pypi.org/project/a2a-sdk/
- **GitHub**: https://github.com/a2aproject/a2a-python
- **A2A Specification**: https://github.com/a2aproject/A2A
- **Official Samples**: https://github.com/a2aproject/a2a-samples

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Starlette Server                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  create_agent_card_routes / create_jsonrpc_routes / │   │
│  │  create_rest_routes  (well-known, JSON-RPC, REST)   │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼──────────────────────────────┐   │
│  │         DefaultRequestHandler                       │   │
│  │     (Routes requests to AgentExecutor)              │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼──────────────────────────────┐   │
│  │         HelloAgentExecutor                          │   │
│  │     (Your custom agent logic)                       │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────┴──────────────────────────────┐   │
│  │  InMemoryTaskStore                                  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 📝 License

Apache 2.0 - See https://github.com/a2aproject/a2a-python for details.
