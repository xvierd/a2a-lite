# File Handling - Google A2A SDK (Python)

> **File upload and processing using the REAL Google A2A SDK.**

This example demonstrates file handling using the official Google A2A SDK with:
- **AgentCard** with file capabilities
- **Custom AgentExecutor** for skill execution
- **Real A2A types** (FilePart, DataPart, TextPart, Task, Message)
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
curl http://localhost:8789/.well-known/agent.json | python -m json.tool
```

### 2. Analyze a File

```bash
curl -X POST http://localhost:8789/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "1",
    "params": {
      "message": {
        "role": "user",
        "message_id": "msg-1",
        "parts": [
          {
            "kind": "text",
            "text": "{\"skill\": \"analyze\"}"
          },
          {
            "kind": "file",
            "file": {
              "name": "test.txt",
              "mimeType": "text/plain",
              "bytes": "SGVsbG8gV29ybGQhCVRoaXMgaXMgYSB0ZXN0IGZpbGUu"
            }
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
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "2",
    "params": {
      "message": {
        "role": "user",
        "message_id": "msg-2",
        "parts": [
          {
            "kind": "text",
            "text": "{\"skill\": \"convert_to_upper\"}"
          },
          {
            "kind": "file",
            "file": {
              "name": "hello.txt",
              "mimeType": "text/plain",
              "bytes": "SGVsbG8gV29ybGQh"
            }
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
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "3",
    "params": {
      "message": {
        "role": "user",
        "message_id": "msg-3",
        "parts": [
          {
            "kind": "data",
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
    AgentSkill,         # Individual skill definition
    AgentCapabilities,  # Feature flags (streaming, push, etc.)
    Task,               # Task lifecycle management
    TaskStatus,         # Task state tracking
    TaskState,          # Enum: submitted, working, completed, etc.
    Message,            # A2A message container
    Part,               # Union of TextPart | FilePart | DataPart
    TextPart,           # Text content
    FilePart,           # File content (bytes or URI)
    DataPart,           # Structured data
    Role,               # user | agent
    Artifact,           # Output artifacts
)

from a2a.server.agent_execution import (
    AgentExecutor,      # Abstract base for agent logic
    RequestContext,     # Execution context
)

from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.apps.jsonrpc import A2AFastAPIApplication
from a2a.server.tasks import InMemoryTaskStore
```

### Custom AgentExecutor

```python
class FileAgentExecutor(AgentExecutor):
    """Custom executor for file processing skills."""
    
    async def execute(self, context: RequestContext, event_queue: EventQueue):
        # Parse message parts
        skill_name, params, file_part = self._parse_message(context.message)
        
        # Execute skill
        if skill_name == "analyze":
            result = await self._execute_analyze(file_part)
        elif skill_name == "convert_to_upper":
            result = await self._execute_convert_to_upper(file_part)
        elif skill_name == "generate_report":
            result = await self._execute_generate_report(params)
        
        # Publish result via event queue
        await self._publish_success(event_queue, task_id, context_id, result)
    
    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        # Handle cancellation requests
        await event_queue.enqueue_event(TaskStatusUpdateEvent(...))
```

### FilePart Handling

```python
from a2a.types import FilePart, FileWithBytes
import base64

def extract_file_from_part(file_part: FilePart) -> Tuple[str, str, bytes]:
    """Extract file data from A2A FilePart."""
    file_data = file_part.file
    
    if isinstance(file_data, FileWithBytes):
        filename = file_data.name or "unknown"
        mime_type = file_data.mime_type or "application/octet-stream"
        content_bytes = base64.b64decode(file_data.bytes)
        return filename, mime_type, content_bytes
    else:
        # FileWithUri - would need to fetch from URI
        raise FileProcessingError("File URI not supported")

def create_file_part(filename: str, mime_type: str, content: bytes) -> FilePart:
    """Create a FilePart for response."""
    return FilePart(
        file=FileWithBytes(
            name=filename,
            mime_type=mime_type,
            bytes=base64.b64encode(content).decode('utf-8')
        )
    )
```

---

## 🔧 Skills

| Skill | Input | Output | Description |
|-------|-------|--------|-------------|
| `analyze` | FilePart | DataPart | Returns file statistics (size, lines, words) |
| `convert_to_upper` | FilePart (text) | FilePart | Returns uppercase version of file |
| `generate_report` | DataPart (format) | FilePart | Generates sample report in txt/csv/json |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    A2AFastAPIApplication                     │
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
