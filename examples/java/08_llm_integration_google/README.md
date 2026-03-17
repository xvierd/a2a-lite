# LLM Integration - Google A2A SDK (Java)

> **Complete LLM-powered agent with conversation memory and tool calling.**

This example demonstrates building an LLM-powered agent using the official Google A2A Java SDK with real OpenAI/Anthropic API integration.

---

## 📋 Complexity Level: **ADVANCED**

**Concepts Covered:**
- LLM integration with OpenAI/Anthropic APIs
- Conversation memory management
- Tool calling support
- Multi-provider support
- Session management

---

## 📁 Files Overview

| File | Purpose | Lines |
|------|---------|-------|
| `LLMAgent.java` | Main agent with HTTP server | ~220 |
| `LLMClient.java` | OpenAI/Anthropic client | ~180 |
| `ConversationManager.java` | Memory management | ~150 |
| `ToolRegistry.java` | Tool definitions & execution | ~120 |
| `pom.xml` | Maven configuration | ~95 |

**Total: ~765 lines across 5 files**

---

## 🚀 Quick Start

### Prerequisites

- Java 17+
- Maven 3.8+
- OpenAI API key or Anthropic API key

### Build

```bash
cd java/08_llm_integration_google
mvn clean package
```

### Run with OpenAI

```bash
export OPENAI_API_KEY="your-openai-key"
export LLM_PROVIDER="openai"
export LLM_MODEL="gpt-4"
java -jar target/llm-agent-google-1.0.0.jar
```

### Run with Anthropic

```bash
export ANTHROPIC_API_KEY="your-anthropic-key"
export LLM_PROVIDER="anthropic"
export LLM_MODEL="claude-3-sonnet-20240229"
java -jar target/llm-agent-google-1.0.0.jar
```

---

## 🧪 Testing

### Chat Request

```bash
curl -X POST http://localhost:8793/ \
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

### Clear Memory

```bash
curl -X POST http://localhost:8793/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "2",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "{\"skill\": \"clear_memory\", \"params\": {}}"}]
      }
    }
  }'
```

### Get Agent Info

```bash
curl -X POST http://localhost:8793/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "3",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "{\"skill\": \"info\", \"params\": {}}"}]
      }
    }
  }'
```

---

## 📖 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    LLMAgent (Main)                          │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │  LLMClient   │  │ConversationManager│  │ ToolRegistry │  │
│  │              │  │                  │  │              │  │
│  │ - OpenAI     │  │ - Session-based  │  │ - Calculator │  │
│  │ - Anthropic  │  │ - Auto-trimming  │  │ - Weather    │  │
│  │ - Tool calls │  │ - Token mgmt     │  │ - Time       │  │
│  └──────────────┘  └──────────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
              ┌──────────┐        ┌──────────┐
              │  Javalin │        │  A2A     │
              │  Server  │        │  Routes  │
              └──────────┘        └──────────┘
```

---

## 🎯 Skills

| Skill | Description | Parameters |
|-------|-------------|------------|
| `chat` | Chat with AI assistant | `message`, `session_id` |
| `clear_memory` | Clear conversation history | `session_id` |
| `info` | Get agent information | (none) |

---

## 🔧 Tools Available

| Tool | Description | Example |
|------|-------------|---------|
| `calculator` | Calculate expressions | "What is 25 * 47?" |
| `get_current_time` | Get current time | "What time is it?" |
| `get_weather` | Get weather (mock) | "What's the weather in Paris?" |

---

## ⚠️ Compare with A2A Lite

See [../08_llm_integration_lite/](../08_llm_integration_lite/) for comparison.

| Aspect | Google SDK | A2A Lite |
|--------|------------|----------|
| **Code Lines** | ~765 lines | ~120 lines |
| **Reduction** | Baseline | **~84% less code** |
| **Memory** | Manual implementation | Built-in |
| **Tool Registration** | Complex registry | Simple builder |
| **LLM Client** | Custom implementation | Pre-built providers |
