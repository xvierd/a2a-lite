# LLM Integration - Google A2A SDK (REAL API)

> **Agent powered by REAL OpenAI/Anthropic APIs with conversation memory and tool calling.**

This example demonstrates a production-ready agent using the official Google A2A Python SDK with real LLM integration. It supports:

- ✅ **Real OpenAI API** (GPT-4, GPT-3.5)
- ✅ **Real Anthropic API** (Claude 3)
- ✅ **Conversation memory** (session-based)
- ✅ **Tool calling** (calculator, weather, time, search)
- ✅ **Multi-turn conversations**

---

## 📋 Requirements

- Python 3.9+
- OpenAI API Key OR Anthropic API Key

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd a2a-lite/examples/python/08_llm_integration_google
pip install -r requirements.txt
```

### 2. Set API Keys

```bash
# For OpenAI
export OPENAI_API_KEY="sk-..."

# OR for Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
```

Optional configuration:
```bash
export LLM_PROVIDER="openai"  # or "anthropic"
export LLM_MODEL="gpt-4"      # or "claude-3-sonnet-20240229"
```

### 3. Run the Agent

```bash
python main.py
```

The agent will start on `http://localhost:8792`

---

## 🧪 Testing

### Test 1: Get Agent Info

```bash
curl -X POST http://localhost:8792/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendMessage",
    "id": "1",
    "params": {
      "message": {
        "messageId": "msg-1",
        "role": "ROLE_USER",
        "parts": [{"text": "{\"skill\": \"info\"}"}]
      }
    }
  }'
```

### Test 2: Simple Chat

```bash
curl -X POST http://localhost:8792/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendMessage",
    "id": "2",
    "params": {
      "message": {
        "messageId": "msg-2",
        "contextId": "test-session-1",
        "role": "ROLE_USER",
        "parts": [{"text": "{\"skill\": \"chat\", \"params\": {\"message\": \"What is the capital of France?\"}}"}]
      }
    }
  }'
```

### Test 3: Chat with Tool Usage

```bash
curl -X POST http://localhost:8792/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendMessage",
    "id": "3",
    "params": {
      "message": {
        "messageId": "msg-3",
        "contextId": "test-session-1",
        "role": "ROLE_USER",
        "parts": [{"text": "{\"skill\": \"chat\", \"params\": {\"message\": \"What is 25 * 47?\"}}"}]
      }
    }
  }'
```

The LLM will automatically call the `calculator` tool and return the result.

### Test 4: Memory Test (Multi-turn)

**First message:**
```bash
curl -X POST http://localhost:8792/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendMessage",
    "id": "4",
    "params": {
      "message": {
        "messageId": "msg-4",
        "contextId": "memory-test",
        "role": "ROLE_USER",
        "parts": [{"text": "{\"skill\": \"chat\", \"params\": {\"message\": \"My name is Alice\"}}"}]
      }
    }
  }'
```

**Second message (same session):**
```bash
curl -X POST http://localhost:8792/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendMessage",
    "id": "5",
    "params": {
      "message": {
        "messageId": "msg-5",
        "contextId": "memory-test",
        "role": "ROLE_USER",
        "parts": [{"text": "{\"skill\": \"chat\", \"params\": {\"message\": \"What is my name?\"}}"}]
      }
    }
  }'
```

The agent should remember that your name is Alice.

### Test 5: Clear Memory

```bash
curl -X POST http://localhost:8792/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendMessage",
    "id": "6",
    "params": {
      "message": {
        "messageId": "msg-6",
        "contextId": "memory-test",
        "role": "ROLE_USER",
        "parts": [{"text": "{\"skill\": \"clear_memory\"}"}]
      }
    }
  }'
```

### Test 6: Agent Card

```bash
curl http://localhost:8792/.well-known/agent-card.json
```

---

## 📁 Files Overview

| File | Purpose |
|------|---------|
| `main.py` | Main application with AgentExecutor, AgentCard, and routing |
| `llm_client.py` | OpenAI and Anthropic API client |
| `conversation.py` | Session-based conversation memory |
| `tools.py` | Tool definitions (calculator, weather, time, search) |
| `requirements.txt` | Dependencies |

---

## 🔧 Architecture

```
┌─────────────┐     A2A Protocol      ┌─────────────────┐
│   Client    │ ────────────────────> │  A2A SDK Server │
└─────────────┘                       └────────┬────────┘
                                              │
                        ┌─────────────────────┼─────────────────────┐
                        │                     │                     │
                        ▼                     ▼                     ▼
                ┌──────────────┐    ┌──────────────┐     ┌──────────────┐
                │  LLM Client  │    │ Conversation │     │   Tools      │
                │(OpenAI/Anth) │    │   Memory     │     │  Registry    │
                └──────────────┘    └──────────────┘     └──────────────┘
```

---

## 🛠️ Available Tools

The LLM can call these tools:

| Tool | Description |
|------|-------------|
| `calculator` | Mathematical calculations (e.g., "25 * 47") |
| `get_weather` | Mock weather data for cities |
| `get_current_time` | Current date and time |
| `search_knowledge` | Search knowledge base |

---

## 🔌 Using Different Models

### OpenAI

```bash
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-4           # or gpt-4-turbo, gpt-3.5-turbo
```

### Anthropic

```bash
export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-3-opus-20240229    # or claude-3-sonnet, claude-3-haiku
```

---

## 📝 Example Response

```json
{
  "response": "25 * 47 = 1,175",
  "session_id": "test-session-1",
  "history_length": 4
}
```

---

## 🔍 Troubleshooting

### "LLM client not configured"
- Set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` environment variable

### Import errors
- Make sure you installed: `pip install -r requirements.txt`
- Verify `a2a-sdk` is installed: `pip show a2a-sdk`

### API errors
- Check your API key is valid
- Verify you have credits on your OpenAI/Anthropic account

---

## 📚 References

- [Google A2A Protocol](https://github.com/google/A2A)
- [A2A Python SDK](https://github.com/a2aproject/a2a-python)
- [OpenAI API Docs](https://platform.openai.com/docs)
- [Anthropic API Docs](https://docs.anthropic.com/)
