# File Handling - Google A2A SDK (Python)

> **File upload and processing using the REAL Google A2A SDK.**

This example demonstrates file handling using the official Google A2A SDK with:
- **AgentCard** with file capabilities
- **Custom AgentExecutor** for skill execution
- **Real A2A v1.0 types** (`Part` with text / raw / url / data, Task, Message)
- File upload/download handling

---

## 📁 Files Overview

| File | Purpose | Lines |
|------|---------|-------|
| `main.py` | Server, AgentExecutor, and routing | ~350 |
| `skills.py` | File processing logic with SDK types | ~170 |
| `requirements.txt` | Dependencies | ~3 |

**Total: ~520 lines across 3 files**

---

## 🚀 Quick Start

```bash
cd a2a-lite/examples/python/03_file_handling_google
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

The server will start on `http://localhost:8789`.

---

## 🧪 Testing

### 1. Get Agent Card

```bash
curl http://localhost:8789/.well-known/agent-card.json | python -m json.tool
```

### 2. Analyze a File

```bash
curl -X POST http://localhost:8789/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendMessage",
    "id": "1",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "msg-1",
        "parts": [
          {
            "text": "{\"skill\": \"analyze\"}"
          },
          {
            "raw": "SGVsbG8gV29ybGQhCVRoaXMgaXMgYSB0ZXN0IGZpbGUu",
            "filename": "test.txt",
            "mediaType": "text/plain"
          }
        ]
      }
    }
  }'
```

### 3. Convert File to Uppercase

```bash
curl -X POST http://localhost:8789/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendMessage",
    "id": "2",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "msg-2",
        "parts": [
          {
            "text": "{\"skill\": \"convert_to_upper\"}"
          },
          {
            "raw": "SGVsbG8gV29ybGQh",
            "filename": "hello.txt",
            "mediaType": "text/plain"
          }
        ]
      }
    }
  }'
```

### 4. Generate a Report

```bash
curl -X POST http://localhost:8789/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendMessage",
    "id": "3",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "msg-3",
        "parts": [
          {
            "data": {
              "skill": "generate_report",
              "params": {"format": "csv"}
            }
          }
        ]
      }
    }
  }'
```

---

## 📖 Implementation Details

### Real A2A SDK Components Used

```python
from a2a.types import (
    AgentCard,          # Agent descriptor with capabilities
    AgentInterface,     # URL + protocol binding exposed by the agent
    AgentSkill,         # Individual skill definition
    AgentCapabilities,  # Feature flags (streaming, push, etc.)
    Task,               # Task lifecycle management
    TaskStatus,         # Task state tracking
    TaskState,          # Enum: TASK_STATE_SUBMITTED, TASK_STATE_WORKING, ...
    Message,            # A2A message container
    Part,               # Single part type: text | raw (bytes) | url | data
    Artifact,           # Output artifacts
)

from a2a.helpers import new_task_from_user_message

from a2a.server.agent_execution import (
    AgentExecutor,      # Abstract base for agent logic
    RequestContext,     # Execution context
)

from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    create_agent_card_routes,
    create_jsonrpc_routes,
    create_rest_routes,
)
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
```

The server is assembled on a plain Starlette app (the old FastAPI
application helpers from a2a-sdk 0.3 were removed in 1.x):

```python
from starlette.applications import Starlette

handler = DefaultRequestHandler(agent_executor, InMemoryTaskStore(), agent_card)
app = Starlette(
    routes=create_agent_card_routes(agent_card)
    + create_jsonrpc_routes(handler, rpc_url="/")
    + create_rest_routes(handler)
)
```

The AgentCard exposes its endpoint via `supported_interfaces` (no root `url`):

```python
AgentCard(
    ...,
    supported_interfaces=[
        AgentInterface(
            url="http://localhost:8789/",
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        ),
    ],
)
```

### Custom AgentExecutor

```python
class FileAgentExecutor(AgentExecutor):
    """Custom executor for file processing skills."""

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        # v1.0 task pattern: enqueue the Task first, then use TaskUpdater
        task = context.current_task or new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        # Parse message parts (single Part type; inspect with HasField())
        skill_name, params, file_part = self._parse_message(context.message)

        # Execute skill
        if skill_name == "analyze":
            result = self._execute_analyze(file_part)
        elif skill_name == "convert_to_upper":
            result = self._execute_convert_to_upper(file_part)
        elif skill_name == "generate_report":
            result = self._execute_generate_report(params)

        # Publish artifacts and complete the task
        await updater.add_artifact([file_or_data_part], name="result")
        await updater.complete(
            message=updater.new_agent_message([Part(text="Done")])
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        # Handle cancellation requests
        task = context.current_task
        if task is not None:
            await TaskUpdater(event_queue, task.id, task.context_id).cancel()
```

### File Part Handling

v1.0 removed `FilePart`/`FileWithBytes`/`DataPart`: a single `Part` carries
text / raw (bytes) / url / data plus `filename` and `media_type` metadata.

```python
from a2a.types import Part

def extract_file_from_part(part: Part) -> Tuple[str, str, bytes]:
    """Extract file data from a v1.0 Part (raw bytes or url)."""
    if part.HasField("raw"):
        filename = part.filename or "unknown"
        mime_type = part.media_type or "application/octet-stream"
        return filename, mime_type, bytes(part.raw)
    elif part.HasField("url"):
        # Remote file reference - would need to fetch from URL
        raise FileProcessingError("File URL not supported")
    raise FileProcessingError("Part does not contain a file")

def create_file_part(filename: str, mime_type: str, content: bytes) -> Part:
    """Create a file-carrying Part for a response or artifact."""
    return Part(
        raw=content,
        filename=filename,
        media_type=mime_type,
    )
```

---

## 🔧 Skills

| Skill | Input | Output | Description |
|-------|-------|--------|-------------|
| `analyze` | File (raw part) | Data part | Returns file statistics (size, lines, words) |
| `convert_to_upper` | File (raw text part) | File part | Returns uppercase version of file |
| `generate_report` | Data part (format) | File part | Generates sample report in txt/csv/json |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 Starlette (route factories)                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           DefaultRequestHandler                       │   │
│  │  ┌────────────────────────────────────────────────┐   │   │
│  │  │         FileAgentExecutor                       │   │   │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────┐  │   │   │
│  │  │  │   analyze   │  │convert_to_  │  │generate_│  │   │   │
│  │  │  │             │  │   upper     │  │ report  │  │   │   │
│  │  │  └─────────────┘  └─────────────┘  └─────────┘  │   │   │
│  │  └────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  InMemoryTaskStore│
                    └─────────────────┘
```

---

## 📚 References

- [A2A Protocol Specification](https://github.com/a2aproject/A2A)
- [A2A Python SDK Documentation](https://github.com/a2aproject/A2A/tree/main/samples/python)
- See [A2A Lite version](../03_file_handling_lite/) for comparison
