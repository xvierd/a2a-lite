# Streaming - Google A2A SDK (Python) - REAL API

> **Real-time streaming responses with Server-Sent Events (SSE) using the official Google A2A Python SDK.**

This example demonstrates how to implement streaming skills using the **real** Google A2A SDK with:
- `A2ARESTFastAPIApplication` - Official FastAPI application builder
- `AgentExecutor.execute()` with `event_queue` for streaming
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
| `main.py` | A2ARESTFastAPIApplication with streaming | ~280 |
| `skills.py` | Streaming async generators | ~200 |
| `requirements.txt` | Dependencies | ~4 |

**Total: ~484 lines across 3 files**

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
# 1. Agent Card with streaming capability
AGENT_CARD = AgentCard(
    name="StreamingAgent",
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
        # Stream chunks via event_queue
        async for chunk in skill_generator():
            await event_queue.enqueue_event(
                new_agent_text_message(json.dumps(chunk))
            )
    
    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        # Handle cancellation
        ...

# 3. FastAPI Application with streaming endpoints
app = A2ARESTFastAPIApplication(
    agent_card=AGENT_CARD,
    http_handler=handler
).build()
```

---

## 🧪 Testing Streaming

### Test 1: Chat Stream (Word by Word)

```bash
curl -N -X POST http://localhost:8791/ \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "1",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "{\"skill\": \"chat\", \"params\": {\"message\": \"Hello world\"}}"}]
      }
    }
  }'
```

**Expected Output:**
```
data: {"type": "token", "content": "You ", "index": 0, "is_last": false}
data: {"type": "token", "content": "said: ", "index": 1, "is_last": false}
data: {"type": "token", "content": "'Hello ", "index": 2, "is_last": false}
...
data: {"type": "done", "skill": "chat"}
```

### Test 2: Count Stream with Progress

```bash
curl -N -X POST http://localhost:8791/ \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "1",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "{\"skill\": \"count\", \"params\": {\"start\": 1, \"end\": 5}}"}]
      }
    }
  }'
```

**Expected Output:**
```
data: {"type": "number", "value": 1, "progress": {"current": 1, "total": 5, "percentage": 20.0}}
data: {"type": "number", "value": 2, "progress": {"current": 2, "total": 5, "percentage": 40.0}}
...
data: {"type": "done", "skill": "count", "final_count": 5}
```

### Test 3: Story Generation Stream

```bash
curl -N -X POST http://localhost:8791/ \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "1",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "{\"skill\": \"story\", \"params\": {\"theme\": \"sci-fi\"}}"}]
      }
    }
  }'
```

### Test 4: Progress Simulation

```bash
curl -N -X POST http://localhost:8791/ \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "1",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "{\"skill\": \"progress\", \"params\": {\"task\": \"data-processing\"}}"}]
      }
    }
  }'
```

---

## 📖 Key Concepts

### 1. Streaming Architecture

The Google A2A SDK handles streaming through the `EventQueue`:

```python
from a2a.server.events.event_queue import EventQueue
from a2a.utils import new_agent_text_message

async def execute(self, context: RequestContext, event_queue: EventQueue):
    # Each enqueue_event sends an SSE chunk to the client
    await event_queue.enqueue_event(
        new_agent_text_message(json.dumps(data))
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

The SDK automatically handles streaming based on the `Accept` header:

- `Accept: text/event-stream` → Streaming response (SSE)
- `Accept: application/json` → Normal response

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
| **Lines** | ~484 | ~50 |
| **Setup** | `AgentExecutor` + `EventQueue` | `@agent.skill(streaming=True)` |
| **Skill Definition** | Manual parsing | Decorator with auto-detection |
| **Streaming** | Manual `event_queue.enqueue_event()` | Automatic `yield` handling |
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
a2a-sdk[http-server]>=0.1.0
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
anyio>=4.0.0
```

Install with: `pip install -r requirements.txt`
