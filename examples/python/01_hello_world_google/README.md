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
  "url": "http://localhost:8787/",
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
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "Hello from A2A!"}]
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
    "id": "task-xxx",
    "status": {
      "state": "completed",
      "message": {
        "role": "agent",
        "parts": [{"kind": "text", "text": "Hello! You said: 'Hello from A2A!'. Welcome to A2A! 👋"}]
      }
    }
  }
}
```

### 3. Verify SDK Installation

```bash
python -c "from a2a.server.apps.rest import A2ARESTFastAPIApplication; print('✅ SDK OK')"
```

## 📚 API Reference

### Core Components

#### 1. AgentCard

```python
from a2a.types import AgentCard, AgentSkill, AgentCapabilities

agent_card = AgentCard(
    name="HelloAgent",
    description="A friendly greeting agent",
    version="1.0.0",
    url="http://localhost:8787/",
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
from a2a.server.events import InMemoryQueueManager
from a2a.server.request_handlers import DefaultRequestHandler

# Create in-memory stores
task_store = InMemoryTaskStore()
queue_manager = InMemoryQueueManager()

# Create request handler
handler = DefaultRequestHandler(
    agent_executor=agent_executor,
    task_store=task_store,
    queue_manager=queue_manager,
)
```

#### 4. FastAPI Application

```python
from a2a.server.apps.rest import A2ARESTFastAPIApplication

app = A2ARESTFastAPIApplication(
    agent_card=agent_card,
    http_handler=handler,
).build()
```

## 📖 Resources

- **PyPI**: https://pypi.org/project/a2a-sdk/
- **GitHub**: https://github.com/a2aproject/a2a-python
- **A2A Specification**: https://github.com/a2aproject/A2A
- **Official Samples**: https://github.com/a2aproject/a2a-samples

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Server                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │         A2ARESTFastAPIApplication                   │   │
│  │              (HTTP REST Endpoint)                   │   │
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
│  │  InMemoryTaskStore  │  InMemoryQueueManager         │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 📝 License

Apache 2.0 - See https://github.com/a2aproject/a2a-python for details.
