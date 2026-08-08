# Streaming - A2A Lite (Python)

> **Real-time streaming with a single decorator.**

This example demonstrates how A2A Lite simplifies streaming implementation using the `streaming=True` parameter and Python's `yield` keyword.

---

## 📋 Complexity Level: **MEDIUM** (simplified!)

**Concepts Covered:**
- Streaming with `@agent.skill(..., streaming=True)`
- `yield` for partial responses
- Automatic SSE formatting
- Client streaming consumption

---

## 📁 Files Overview

| File | Purpose | Lines |
|------|---------|-------|
| `agent.py` | Complete streaming agent | ~50 |
| `requirements.txt` | Dependencies | ~2 |
| `test_streaming.py` | Tests | ~25 |

**Total: ~77 lines across 3 files**

Compare to Google SDK: **~364 lines → 79% reduction!**

---

## 🚀 Quick Start

```bash
cd python/06_streaming_lite
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python agent.py
```

---

## 🧪 Testing Streaming

### Test Chat Stream

```bash
curl -N -X POST http://localhost:8791/ \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendStreamingMessage",
    "id": "1",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "msg-1",
        "parts": [{"text": "{\"skill\": \"chat\", \"params\": {\"message\": \"Hello\"}}"}]
      }
    }
  }'

# Expected: Word-by-word streaming response
```

### Test with Python Client

```python
from a2a_lite import AgentTestClient

client = AgentTestClient(agent)
chunks = client.stream("chat", message="Hello world")

for chunk in chunks:
    print(chunk)  # Each word as it arrives
```

---

## 📖 Code Comparison

### Google SDK Approach

```python
# sse_utils.py - Manual SSE formatting
def format_sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"

# main.py - Complex streaming setup
@app.post("/")
async def handle(request):
    generator = get_skill_generator(skill_name, params)
    
    if wants_streaming:
        return StreamingResponse(
            stream_skill(generator),
            media_type="text/event-stream",
            headers={...}
        )
    else:
        chunks = []
        async for chunk in generator:
            chunks.append(chunk)
        return chunks
```

### A2A Lite Approach

```python
# Just use streaming=True and yield!
@agent.skill("chat", streaming=True)
async def chat(message: str):
    words = generate_response(message)
    for word in words:
        yield {"token": word}
        await asyncio.sleep(0.1)
```

---

## 🎯 How It Works

### 1. Mark Skill as Streaming

```python
@agent.skill("stream_name", streaming=True)
```

### 2. Use `yield` Instead of `return`

```python
@agent.skill("count", streaming=True)
async def count(start: int, end: int):
    for i in range(start, end + 1):
        yield {"number": i, "progress": i / end * 100}
        await asyncio.sleep(0.5)
```

### 3. A2A Lite Handles Everything Else

- ✅ SSE protocol formatting
- ✅ Connection management
- ✅ Chunk encoding
- ✅ Error handling in streams

---

## 📊 Comparison Summary

| Aspect | Google SDK | A2A Lite |
|--------|------------|----------|
| **Lines** | ~364 | ~77 |
| **Files** | 4 | 3 |
| **Setup** | Manual SSE handling | `streaming=True` |
| **Generator** | Async generator | `yield` keyword |
| **Testing** | Complex | `client.stream()` |

See [Google SDK version](../06_streaming_google/) for comparison.
