# LLM Integration - A2A Lite (Python)

> **LLM-powered agent with minimal boilerplate.**

This example demonstrates how A2A Lite simplifies building LLM-powered agents using the `@openai_skill` / `@anthropic_skill` decorators — no custom LLM client, no manual SSE.

---

## 📋 Complexity Level: **ADVANCED** (simplified!)

**Concepts Covered:**
- LLM integration with `a2a_lite.llm` decorators
- Multi-provider support (OpenAI/Anthropic)
- Token streaming with `streaming=True`
- Lazy provider imports (the agent starts without API keys)

---

## 📁 Files Overview

| File | Purpose | Lines |
|------|---------|-------|
| `agent.py` | Complete LLM agent | ~110 |
| `requirements.txt` | Dependencies | ~4 |

**Total: ~114 lines across 2 files**

Compare to Google SDK: **~377 lines (main.py) → 70% reduction!**

---

## 🚀 Quick Start

```bash
cd python/08_llm_integration_lite
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

export OPENAI_API_KEY="your-key"
python agent.py
```

The provider package is only needed at call time:
`pip install a2a-lite[openai]` (default) or `a2a-lite[anthropic]`
(select with `LLM_PROVIDER=anthropic`, model with `LLM_MODEL`).

---

## 🧪 Testing

```bash
# Simple chat (requires OPENAI_API_KEY)
curl -X POST http://localhost:8792/ \
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
        "parts": [{"text": "{\"skill\": \"chat\", \"params\": {\"message\": \"Hello!\"}}"}]
      }
    }
  }'

# Agent configuration (no API key needed)
curl -X POST http://localhost:8792/ \
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
        "parts": [{"text": "{\"skill\": \"info\"}"}]
      }
    }
  }'
```

---

## 📖 Code Comparison

### Google SDK Approach

```python
# ~377 lines (main.py) + llm_client.py + conversation.py + tools.py
# Custom LLM client, manual conversation memory, TaskUpdater plumbing
```

### A2A Lite Approach

```python
from a2a_lite import Agent
from a2a_lite.llm import openai_skill

agent = Agent(name="LLMAgent", description="AI assistant", version="1.0.0")

@agent.skill("chat")
@openai_skill(model="gpt-4o-mini", system_prompt="You are helpful.")
async def chat(message: str) -> str:
    ...  # handled by the decorator

# Streaming is one extra flag:
@agent.skill("chat_stream", streaming=True)
@openai_skill(model="gpt-4o-mini", streaming=True)
async def chat_stream(message: str) -> str:
    ...
```

---

## 🎯 How A2A Lite Simplifies LLM Integration

| Feature | Google SDK | A2A Lite |
|---------|------------|----------|
| **LLM Client** | Custom implementation | `@openai_skill` / `@anthropic_skill` |
| **Provider Switch** | Code changes | `LLM_PROVIDER` env var |
| **Streaming** | Manual SSE + TaskUpdater | `streaming=True` |
| **Wiring** | DefaultRequestHandler + routes | `agent.run()` |

See [Google SDK version](../08_llm_integration_google/) for comparison.

**Note**: unlike the Google SDK example (which implements conversation
memory and tool calling by hand), the A2A Lite decorators cover the
single-shot LLM call. For memory/tools, compose them in your own skill
code or use the Google SDK example as reference.
