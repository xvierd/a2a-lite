# Streaming Agent - Google A2A SDK

This example demonstrates **Server-Sent Events (SSE) streaming** using the official Google A2A Java SDK.

## Overview

The Google SDK approach requires building all streaming infrastructure manually:
- SSE connection management
- Event emitters and formatters
- Client tracking and cleanup
- Manual streaming logic per skill

## Project Structure

```
06_streaming_google/
├── pom.xml                                    # Maven configuration
├── README.md                                  # This file
└── src/main/java/com/example/streaming/
    ├── StreamingAgent.java                    # Main agent (400+ lines)
    ├── sse/
    │   └── SseEventEmitter.java              # SSE infrastructure (150+ lines)
    └── skills/
        ├── ChatSkill.java                    # Chat streaming
        ├── CountSkill.java                   # Count streaming
        ├── StorySkill.java                   # Story streaming
        └── ProgressSkill.java                # Progress streaming
```

## Key Features

### AgentCapabilities with streaming=true

```java
ObjectNode capabilities = mapper.createObjectNode();
capabilities.put("streaming", true);           // Enable streaming
capabilities.put("pushNotifications", false);
card.set("capabilities", capabilities);
```

### SSE Infrastructure

The `SseEventEmitter` class handles:
- Event formatting (`event: name\ndata: json\n\n`)
- Connection state management
- Error handling
- Multiple event types (chunk, token, progress, status)

### Streaming Endpoints

```
GET  /.well-known/agent.json    # Agent discovery with streaming=true
POST /                         # Standard JSON-RPC messages
POST /stream                   # Initiate streaming task
GET  /stream/{taskId}          # SSE connection for events
```

## Building

```bash
mvn clean package
```

## Running

```bash
mvn exec:java
# or
java -jar target/streaming-agent-google-1.0.0.jar
```

## Testing Streaming

### Using curl

**1. Check agent card:**
```bash
curl http://localhost:8787/.well-known/agent.json
```

**2. Initiate streaming:**
```bash
curl -X POST http://localhost:8787/stream \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "message/send",
    "params": {
      "skill": "chat",
      "message": "Hello streaming!"
    }
  }'
```

Response:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "taskId": "task-1234567890-...",
    "streamUrl": "http://localhost:8787/stream/task-1234567890-...",
    "status": "streaming"
  }
}
```

**3. Connect to SSE stream:**
```bash
curl -N http://localhost:8787/stream/task-1234567890-...
```

### Using JavaScript EventSource

```javascript
// 1. Initiate streaming
const response = await fetch('/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    jsonrpc: '2.0',
    id: 1,
    method: 'message/send',
    params: { skill: 'chat', message: 'Hello!' }
  })
});
const { result } = await response.json();

// 2. Connect to SSE
const evtSource = new EventSource(result.streamUrl);

evtSource.addEventListener('token', (e) => {
  const data = JSON.parse(e.data);
  console.log('Token:', data.token);
});

evtSource.addEventListener('progress', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Progress: ${data.percent}%`);
});

evtSource.addEventListener('complete', (e) => {
  evtSource.close();
});
```

## Available Skills

| Skill | Description | Events |
|-------|-------------|--------|
| `chat` | Interactive chat | `token`, `status`, `complete` |
| `count` | Count with progress | `progress`, `chunk`, `complete` |
| `story` | Word-by-word story | `token`, `status`, `complete` |
| `progress` | Multi-step progress | `progress`, `step_started`, `step_complete` |

## Code Statistics

- **Total Files**: 6 Java files
- **Total Lines of Code**: ~800 lines
- **Infrastructure Code**: ~550 lines (SseEventEmitter + StreamingAgent setup)
- **Skill Logic**: ~250 lines
- **Complexity**: High (manual SSE management)

## Comparison with A2A Lite

| Aspect | Google SDK | A2A Lite |
|--------|------------|----------|
| Lines of Code | ~800 | ~100 |
| Infrastructure | Manual | Built-in |
| SSE Management | Hand-crafted | Automatic |
| Skill Definition | Complex | Simple lambda |
| Event Types | Custom implementation | Pre-defined |
| Client Tracking | Manual | Handled by framework |
