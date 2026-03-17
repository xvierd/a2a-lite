# LLM Agent - A2A Lite (Java)

LLM-powered agent with memory and tools using the **real A2A Lite library**.

## Features

- Conversation memory (per session)
- Tool calling (calculator, time, weather)
- Multi-turn conversations

## Configuration

```bash
export OPENAI_API_KEY="your-key-here"
# or
export ANTHROPIC_API_KEY="your-key-here"

export LLM_PROVIDER="openai"  # or "anthropic"
export LLM_MODEL="gpt-4o-mini"  # or "claude-3-sonnet"
```

## Running

```bash
./gradlew run
```

## API

```bash
curl -X POST http://localhost:8794/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "parts": [{"type": "text", "text": "{\"skill\": \"chat\", \"params\": {\"message\": \"What time is it?\", \"session_id\": \"user123\"}}"}]
      }
    }
  }'
```
