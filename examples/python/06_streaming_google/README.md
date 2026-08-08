# Streaming - Google A2A SDK (Python) - REAL API

> **Real-time streaming responses with Server-Sent Events (SSE) using the official Google A2A Python SDK.**

This example demonstrates how to implement streaming skills using the **real** Google A2A SDK (A2A protocol v1.0) with:
- Starlette routes via `create_agent_card_routes` / `create_jsonrpc_routes` / `create_rest_routes` - Official SDK route builders
- `AgentExecutor.execute()` with `event_queue` + `TaskUpdater` for streaming
- `AgentCard` with streaming capabilities
- Proper SSE (Server-Sent Events) implementation

---

## 📋 Complexity Level: **MEDIUM**

**Concepts Covered:**
- Official A2A SDK streaming architecture
- `AgentExecutor` with `event_queue`
- Server-Sent Events (SSE) via SDK
- Async generators for streaming
- Connection management
- Client-side streaming consumption

---

## 📁 Files Overview

| File | Purpose | Lines |
|------|---------|-------|
| `main.py` | Starlette app with streaming routes | ~270 |
| `skills.py` | Streaming async generators | ~260 |
| `requirements.txt` | Dependencies | ~11 |

**Total: ~541 lines across 3 files**

---

## 🚀 Quick Start

```bash
cd python/06_streaming_google
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

The server will start on `http://localhost:8791`

---

## 🏗️ Architecture

### Real SDK Components Used

```python
# 1. Agent Card with streaming capability (v1.0)
AGENT_CARD = AgentCard(
    name="StreamingAgent",
    supported_interfaces=[
        AgentInterface(
            url="http://localhost:8791/",
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        ),
    ],
    capabilities=AgentCapabilities(
        streaming=True,  # Enable streaming
    ),
    skills=[...]
)

# 2. Custom AgentExecutor with streaming support
class StreamingAgentExecutor(AgentExecutor):
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,  # Key for streaming!
    ) -> None:
        # First event must be the Task itself (strict v1.0 rule)
        task = context.current_task or new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        # Stream chunks as WORKING status updates
        async for chunk in skill_generator():
            await updater.update_status(
                TaskState.TASK_STATE_WORKING,
                message=updater.new_agent_message([new_text_part(json.dumps(chunk))]),
            )
        await updater.complete()
    
    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        # Handle cancellation
        ...

# 3. Starlette Application with streaming endpoints
handler = DefaultRequestHandler(
    agent_executor=agent_executor,
    task_store=InMemoryTaskStore(),
    agent_card=AGENT_CARD,
)
app = Starlette(
    routes=create_agent_card_routes(AGENT_CARD)
    + create_jsonrpc_routes(handler, rpc_url="/")
    + create_rest_routes(handler)
)
```

---

## 🧪 Testing Streaming

### Test 1: Chat Stream (Word by Word)

```bash
curl -N -X POST http://localhost:8791/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -H "Accept: text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendStreamingMessage",
    "id": "1",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "msg-1",
        "parts": [{"text": "{\"skill\": \"chat\", \"params\": {\"message\": \"Hello world\"}}"}]
      }
    }
  }'
```

**Expected Output:**
```
data: {"result": {"statusUpdate": {"taskId": "...", "status": {"state": "TASK_STATE_WORKING", "message": {"role": "ROLE_AGENT", "parts": [{"text": "{\"type\": \"token\", \"content\": \"You \", \"index\": 0, \"is_last\": false}"}]}}}}}
data: {"result": {"statusUpdate": {"taskId": "...", "status": {"state": "TASK_STATE_WORKING", "message": {"role": "ROLE_AGENT", "parts": [{"text": "{\"type\": \"token\", \"content\": \"said: \", \"index\": 1, \"is_last\": false}"}]}}}}}
...
data: {"result": {"statusUpdate": {"taskId": "...", "status": {"state": "TASK_STATE_COMPLETED", "message": {...}}}}}
```

### Test 2: Count Stream with Progress

```bash
curl -N -X POST http://localhost:8791/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -H "Accept: text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendStreamingMessage",
    "id": "1",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "msg-2",
        "parts": [{"text": "{\"skill\": \"count\", \"params\": {\"start\": 1, \"end\": 5}}"}]
      }
    }
  }'
```

**Expected Output:**
```
data: {"result": {"statusUpdate": {"taskId": "...", "status": {"state": "TASK_STATE_WORKING", "message": {"role": "ROLE_AGENT", "parts": [{"text": "{\"type\": \"number\", \"value\": 1, \"progress\": {\"current\": 1, \"total\": 5, \"percentage\": 20.0}}"}]}}}}}
data: {"result": {"statusUpdate": {"taskId": "...", "status": {"state": "TASK_STATE_WORKING", "message": {"role": "ROLE_AGENT", "parts": [{"text": "{\"type\": \"number\", \"value\": 2, \"progress\": {\"current\": 2, \"total\": 5, \"percentage\": 40.0}}"}]}}}}}
...
data: {"result": {"statusUpdate": {"taskId": "...", "status": {"state": "TASK_STATE_COMPLETED", "message": {...}}}}}
```

### Test 3: Story Generation Stream

```bash
curl -N -X POST http://localhost:8791/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -H "Accept: text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendStreamingMessage",
    "id": "1",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "msg-3",
        "parts": [{"text": "{\"skill\": \"story\", \"params\": {\"theme\": \"sci-fi\"}}"}]
      }
    }
  }'
```

### Test 4: Progress Simulation

```bash
curl -N -X POST http://localhost:8791/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -H "Accept: text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendStreamingMessage",
    "id": "1",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "msg-4",
        "parts": [{"text": "{\"skill\": \"progress\", \"params\": {\"task\": \"data-processing\"}}"}]
      }
    }
  }'
```

---

## 📖 Key Concepts

### 1. Streaming Architecture

The Google A2A SDK handles streaming through the `EventQueue`:

```python
from a2a.helpers import new_task_from_user_message, new_text_part
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState

async def execute(self, context: RequestContext, event_queue: EventQueue):
    # First event must be the Task itself (strict v1.0 rule)
    task = context.current_task or new_task_from_user_message(context.message)
    await event_queue.enqueue_event(task)
    updater = TaskUpdater(event_queue, task.id, task.context_id)
    # Each update_status sends an SSE chunk to the client
    await updater.update_status(
        TaskState.TASK_STATE_WORKING,
        message=updater.new_agent_message([new_text_part(json.dumps(data))]),
    )
```

### 2. Async Generators for Skills

Skills use async generators to yield partial results:

```python
async def chat_stream(message: str):
    words = generate_response(message)
    
    for i, word in enumerate(words):
        yield {
            "type": "token",
            "content": word + " ",
            "index": i
        }
        await asyncio.sleep(0.1)
    
    yield {"type": "done"}
```

### 3. Client Capability Detection

The SDK handles streaming based on the JSON-RPC method:

- `SendStreamingMessage` → Streaming response (SSE)
- `SendMessage` → Normal (non-streaming) response

---

## 🔧 Implementation Details

### Skill Execution Flow

1. **Request received** → `DefaultRequestHandler`
2. **Task created** → `InMemoryTaskStore`
3. **Executor called** → `StreamingAgentExecutor.execute()`
4. **Skill generator** → yields chunks
5. **Event queue** → sends SSE events
6. **Client receives** → stream of data chunks

### Event Queue Flow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Client    │────▶│ A2A SDK      │────▶│  Handler    │
│  Request    │     │  Server      │     │             │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                │
                       ┌────────────────────────┘
                       ▼
              ┌─────────────────┐
              │ StreamingAgent  │
              │   Executor      │
              └────────┬────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    ┌─────────┐  ┌─────────┐  ┌─────────┐
    │  Chat   │  │  Count  │  │  Story  │  (async generators)
    └────┬────┘  └────┬────┘  └────┬────┘
         │            │            │
         └────────────┼────────────┘
                      ▼
              ┌───────────────┐
              │  EventQueue   │  (SSE stream)
              │ enqueue_event │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │     Client    │
              │  (SSE events) │
              └───────────────┘
```

---

## 📊 Comparison: Real SDK vs A2A Lite

| Aspect | Google A2A SDK (This Example) | A2A Lite |
|--------|------------------------------|----------|
| **Lines** | ~541 | ~50 |
| **Setup** | `AgentExecutor` + `EventQueue` | `@agent.skill(streaming=True)` |
| **Skill Definition** | Manual parsing | Decorator with auto-detection |
| **Streaming** | Manual `TaskUpdater.update_status()` | Automatic `yield` handling |
| **Flexibility** | Full control | Convention over configuration |
| **Use Case** | Complex custom logic | Quick prototyping |

---

## 🔗 References

- [Google A2A Python SDK](https://github.com/a2aproject/a2a-python)
- [A2A Specification](https://github.com/a2aproject/a2a-spec)
- [A2A Lite Version](../06_streaming_lite/) - Simplified streaming

---

## 📝 Requirements

```
a2a-sdk[http-server]>=1.1.2,<2.0
uvicorn[standard]>=0.23.0
anyio>=4.0.0
httpx>=0.27.0
```

Install with: `pip install -r requirements.txt`
