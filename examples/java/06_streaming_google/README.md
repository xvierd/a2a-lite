# Streaming Agent - A2A v1.0 (from scratch, no SDK)

This example demonstrates **Server-Sent Events (SSE) streaming** implementing the
**A2A protocol v1.0 wire format by hand** with Javalin + Jackson — no SDK. For the
official Java SDK approach see `packages/java` (LiteAgentExecutor / Quarkus
integration).

## Overview

The from-scratch approach requires building all streaming infrastructure manually:
- SSE event formatting (`data: {...}` lines on the RPC HTTP response)
- v1.0 task lifecycle (task / statusUpdate / artifactUpdate events)
- Task and context ID management
- Manual streaming logic per skill

## Project Structure

```
06_streaming_google/
├── pom.xml                                    # Maven configuration
├── README.md                                  # This file
└── src/main/java/com/example/streaming/
    ├── StreamingAgent.java                    # Main agent + JSON-RPC routing
    ├── sse/
    │   ├── StreamEmitter.java                 # Skill output sink (interface)
    │   ├── SseEventEmitter.java               # v1.0 SSE event emitter
    │   └── CollectingEmitter.java             # Buffer for sync SendMessage
    └── skills/
        ├── ChatSkill.java                     # Chat streaming
        ├── CountSkill.java                    # Count streaming
        ├── StorySkill.java                    # Story streaming
        └── ProgressSkill.java                 # Progress streaming
```

## Key Features

### Agent card with streaming=true

Served at `GET /.well-known/agent-card.json` (v1.0 shape):

```json
{
  "name": "StreamingAgent",
  "description": "Streaming agent demonstrating SSE (A2A v1.0 from scratch)",
  "version": "1.0.0",
  "supportedInterfaces": [
    {"url": "http://localhost:8787/", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
  ],
  "skills": [
    {"id": "chat", "name": "chat", "description": "...", "tags": ["chat", "streaming"]}
  ],
  "capabilities": {"streaming": true, "pushNotifications": false},
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"]
}
```

### v1.0 SSE events

`SendStreamingMessage` streams `data: {...}` lines directly on the POST response.
Each line is a JSON-RPC-style envelope whose `result` has exactly one key:

| Key | Payload | When |
|-----|---------|------|
| `task` | `{"id", "contextId", "status": {"state": "TASK_STATE_SUBMITTED", ...}, "artifacts": []}` | Always the first event |
| `statusUpdate` | `{"taskId", "contextId", "status": {"state": "TASK_STATE_*", "timestamp", "message": {...}}}` | Working progress, completion, failure |
| `artifactUpdate` | `{"taskId", "artifact": {"artifactId", "name", "parts": [{"text": ...}]}, "append": true, "lastChunk": false}` | Incremental result chunks |

There is **no `final` field** — closing the stream signals terminality. Task
states use the v1.0 enum form: `TASK_STATE_SUBMITTED`, `TASK_STATE_WORKING`,
`TASK_STATE_COMPLETED`, `TASK_STATE_FAILED`.

### Endpoints

```
GET  /.well-known/agent-card.json   # Agent discovery (v1.0)
POST /                               # JSON-RPC: SendMessage / SendStreamingMessage
```

Every RPC response carries the `A2A-Version: 1.0` header.

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

## Testing

### Using curl

**1. Check agent card:**
```bash
curl http://localhost:8787/.well-known/agent-card.json
```

**2. SendMessage (synchronous):**
```bash
curl -X POST http://localhost:8787/ \
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
        "parts": [{"text": "{\"skill\": \"chat\", \"params\": {\"message\": \"hello\"}}"}]
      }
    }
  }'
```

Response:
```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "result": {
    "message": {
      "messageId": "<uuid>",
      "role": "ROLE_AGENT",
      "parts": [{"text": "Hello! Welcome to the streaming chat demo..."}]
    }
  }
}
```

**3. SendStreamingMessage (SSE):**
```bash
curl -N -X POST http://localhost:8787/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "id": "2",
    "method": "SendStreamingMessage",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "m2",
        "parts": [{"text": "{\"skill\": \"count\", \"params\": {\"to\": 5}}"}]
      }
    }
  }'
```

Stream output (one `data:` line per event):
```
data: {"result":{"task":{"id":"...","contextId":"...","status":{"state":"TASK_STATE_SUBMITTED",...},"artifacts":[]}}}

data: {"result":{"statusUpdate":{"taskId":"...","contextId":"...","status":{"state":"TASK_STATE_WORKING","timestamp":"...","message":{"messageId":"...","role":"ROLE_AGENT","parts":[{"text":"Starting count to 5"}]}}}}}

data: {"result":{"artifactUpdate":{"taskId":"...","artifact":{"artifactId":"...","name":"response","parts":[{"text":"1 "}]},"append":true,"lastChunk":false}}}

...

data: {"result":{"statusUpdate":{"taskId":"...","contextId":"...","status":{"state":"TASK_STATE_COMPLETED","timestamp":"...","message":{...,"parts":[{"text":"Finished counting to 5"}]}}}}}
```

### Using JavaScript (fetch + ReadableStream)

`EventSource` cannot POST, so consume the stream with `fetch`:

```javascript
const response = await fetch('/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'A2A-Version': '1.0' },
  body: JSON.stringify({
    jsonrpc: '2.0',
    id: '1',
    method: 'SendStreamingMessage',
    params: {
      message: {
        role: 'ROLE_USER',
        messageId: 'm1',
        parts: [{ text: JSON.stringify({ skill: 'chat', params: { message: 'hello' } }) }]
      }
    }
  })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
while (true) {
  const { done, value } = await reader.read();
  if (done) break; // stream close = terminal
  for (const line of decoder.decode(value).split('\n')) {
    if (line.startsWith('data: ')) {
      const event = JSON.parse(line.slice(6));
      if (event.result.task) console.log('Task:', event.result.task.id);
      if (event.result.statusUpdate) console.log('Status:', event.result.statusUpdate.status.state);
      if (event.result.artifactUpdate) process.stdout.write(event.result.artifactUpdate.artifact.parts[0].text);
    }
  }
}
```

## Available Skills

| Skill | Description | Streaming pattern |
|-------|-------------|-------------------|
| `chat` | Interactive chat | `artifactUpdate` per word, `statusUpdate` for status |
| `count` | Count with progress | `statusUpdate` progress + `artifactUpdate` per number |
| `story` | Word-by-word story | `artifactUpdate` per word |
| `progress` | Multi-step progress | `statusUpdate` per step and percent |

Skill calls travel inside the text part as JSON:
`{"skill": "<name>", "params": {...}}`.

## Comparison with A2A Lite

| Aspect | From scratch (this example) | A2A Lite |
|--------|------------------------------|----------|
| Lines of Code | ~700 | ~100 |
| Infrastructure | Manual | Built-in |
| SSE Management | Hand-crafted | Automatic |
| Skill Definition | Complex | Simple lambda |
| Event Types | Custom implementation | Pre-defined |
| Client Tracking | Manual | Handled by framework |
