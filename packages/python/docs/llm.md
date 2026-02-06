# LLM Integration

A2A Lite provides decorators that wrap skills to call LLM APIs. The actual API call is handled by the decorator — your skill body can be empty.

## Installation

```bash
pip install a2a-lite[openai]     # For OpenAI
pip install a2a-lite[anthropic]  # For Anthropic
# Ollama uses httpx (already included)
```

## OpenAI

### Basic Usage

```python
from a2a_lite.llm import openai_skill

@agent.skill("chat")
@openai_skill(model="gpt-4o-mini", system_prompt="You are helpful.")
async def chat(message: str) -> str:
    ...  # Handled by decorator
```

### Streaming

```python
@agent.skill("chat", streaming=True)
@openai_skill(model="gpt-4o-mini", streaming=True)
async def chat(message: str) -> str:
    ...  # Streams tokens automatically
```

### Parameters

| Param | Default | Description |
|-------|---------|-------------|
| `model` | `"gpt-4o-mini"` | OpenAI model ID |
| `system_prompt` | `"You are a helpful assistant."` | System message |
| `temperature` | `0.7` | Sampling temperature |
| `max_tokens` | `None` | Max response tokens |
| `streaming` | `False` | Stream tokens |

## Anthropic

### Basic Usage

```python
from a2a_lite.llm import anthropic_skill

@agent.skill("analyze")
@anthropic_skill(model="claude-sonnet-4-5-20250929", max_tokens=1024)
async def analyze(text: str) -> str:
    ...  # Handled by decorator
```

### Streaming

```python
@agent.skill("chat", streaming=True)
@anthropic_skill(model="claude-sonnet-4-5-20250929", streaming=True)
async def chat(message: str) -> str:
    ...  # Streams tokens automatically
```

### Parameters

| Param | Default | Description |
|-------|---------|-------------|
| `model` | `"claude-sonnet-4-5-20250929"` | Anthropic model ID |
| `system_prompt` | `"You are a helpful assistant."` | System message |
| `temperature` | `0.7` | Sampling temperature |
| `max_tokens` | `1024` | Max response tokens |
| `streaming` | `False` | Stream tokens |

## Ollama (Local)

No extra dependencies needed — uses httpx.

```python
from a2a_lite.llm import ollama_skill

@agent.skill("local_chat")
@ollama_skill(model="llama3.2", base_url="http://localhost:11434")
async def local_chat(message: str) -> str:
    ...  # Calls local Ollama
```

### Parameters

| Param | Default | Description |
|-------|---------|-------------|
| `model` | `"llama3.2"` | Ollama model name |
| `base_url` | `"http://localhost:11434"` | Ollama server URL |
| `system_prompt` | `"You are a helpful assistant."` | System message |
| `temperature` | `0.7` | Sampling temperature |
| `streaming` | `False` | Stream tokens |

## Message Extraction

The decorators look for the user's input in skill parameters by checking these keys in order: `message`, `text`, `query`, `prompt`, `input`. Falls back to the first string parameter.

## Examples

- [`examples/15_llm_openai.py`](https://github.com/a2a-lite/a2a-lite/blob/main/packages/python/examples/15_llm_openai.py) — OpenAI with streaming
- [`examples/16_llm_anthropic.py`](https://github.com/a2a-lite/a2a-lite/blob/main/packages/python/examples/16_llm_anthropic.py) — Anthropic integration
