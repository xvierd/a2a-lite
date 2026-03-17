# LLM Integration - A2A Lite (Python)

> **LLM-powered agent with minimal boilerplate.**

This example demonstrates how A2A Lite simplifies building LLM-powered agents with built-in support for conversation memory, tool calling, and multi-provider integration.

---

## 📋 Complexity Level: **ADVANCED** (simplified!)

**Concepts Covered:**
- LLM integration with `llm=` parameter
- Automatic conversation memory
- Tool registration with decorators
- Multi-provider support (OpenAI/Anthropic)

---

## 📁 Files Overview

| File | Purpose | Lines |
|------|---------|-------|
| `agent.py` | Complete LLM agent | ~90 |
| `requirements.txt` | Dependencies | ~4 |
| `tools.py` | Tool definitions | ~60 |

**Total: ~154 lines across 3 files**

Compare to Google SDK: **~686 lines → 78% reduction!**

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

---

## 🧪 Testing

```bash
# Simple chat
curl -X POST http://localhost:8792/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "1",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "{\"skill\": \"chat\", \"params\": {\"message\": \"Hello!\"}}"}]
      }
    }
  }'
```

---

## 📖 Code Comparison

### Google SDK Approach

```python
# ~686 lines across 6 files
# Manual conversation management
# Custom LLM client
# Tool registry implementation
# Complex routing
```

### A2A Lite Approach

```python
from a2a_lite import Agent, OpenAIClient
from a2a_lite.tools import tool

agent = Agent(
    name="LLMAgent",
    llm=OpenAIClient(model="gpt-4"),
    conversation_memory=True  # One line!
)

@tool
def calculator(expression: str) -> str:
    return str(eval(expression))

agent.add_tool(calculator)
```

---

## 🎯 How A2A Lite Simplifies LLM Integration

| Feature | Google SDK | A2A Lite |
|---------|------------|----------|
| **Memory** | Manual session management | `conversation_memory=True` |
| **Tools** | Complex registry | `@tool` decorator |
| **LLM Client** | Custom implementation | Built-in providers |
| **Context** | Manual message building | Automatic |
| **Streaming** | Manual SSE | `streaming=True` |

See [Google SDK version](../08_llm_integration_google/) for comparison.
