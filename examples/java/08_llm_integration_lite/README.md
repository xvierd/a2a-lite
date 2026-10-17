# LLM Agent - A2A Lite (Java)

Simulated assistant with local conversation memory and tool routing using the **real A2A Lite library**. This example does not call an LLM provider, even when API-key variables are present.

## Features

- Process-local history per session, trimmed to recent messages
- Keyword routing to a calculator, current time and simulated weather
- Simulated responses; history is not sent to a model

The sample's session map has no ownership checks, session-count bound or restart persistence. Treat it as a single-user learning example. For managed runtime and durable protocol state, continue with [example 11](../11_production_path_lite/).

## Configuration

```bash
# The demo checks only that this variable exists; no real credential is needed.
export OPENAI_API_KEY="simulation-only"
export LLM_PROVIDER="openai"  # informational metadata in this demo
export LLM_MODEL="simulation"
```

## Running

```bash
# From the repository root; resolves the local 1.2.0 library via composite build
cd examples/java
./gradlew :08_llm_integration_lite:run
```

## API

```bash
curl -X POST http://localhost:8794/ \
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
        "parts": [{"text": "{\"skill\": \"chat\", \"params\": {\"message\": \"What time is it?\", \"session_id\": \"user123\"}}"}]
      }
    }
  }'
```
