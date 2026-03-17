# Calculator - A2A Lite (Python)

> **Multi-skill calculator in a single file using A2A Lite.**

This example demonstrates the same calculator functionality as the Google SDK version but with A2A Lite's simplified API. Compare the two to see how A2A Lite reduces code by ~82% while adding features like auto-generated schemas and built-in testing.

---

## 📁 Files Overview

| File | Purpose | Lines |
|------|---------|-------|
| `agent.py` | Complete calculator agent | ~40 |
| `requirements.txt` | Dependencies | ~2 |
| `test_calculator.py` | Unit tests (no HTTP!) | ~25 |

**Total: ~67 lines across 3 files**

Compare to Google SDK: **~223 lines → 70% less code!**

---

## 🚀 Quick Start

```bash
cd python/02_calculator_lite
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python agent.py
```

Agent starts at `http://localhost:8788`

---

## 🧪 Testing

### Method 1: Built-in TestClient (Recommended)

```bash
python test_calculator.py
```

No HTTP server needed! Tests run in milliseconds.

### Method 2: curl

```bash
# Addition
curl -X POST http://localhost:8788/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "1",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "{\"skill\": \"add\", \"params\": {\"a\": 10, \"b\": 5}}"}],
        "messageId": "msg-1"
      }
    }
  }'

# Check auto-generated agent card
curl http://localhost:8788/.well-known/agent.json
```

---

## 📖 Code Walkthrough

### Complete Agent

```python
from a2a_lite import Agent

agent = Agent(name="Calculator", description="Arithmetic operations")

@agent.skill("add")
async def add(a: float, b: float) -> dict:
    return {"result": a + b}

@agent.skill("divide")
async def divide(a: float, b: float) -> dict:
    if b == 0:
        raise ValueError("Division by zero")
    return {"result": a / b, "remainder": a % b}

agent.run(port=8788)
```

### What A2A Lite Handles Automatically

| Task | Google SDK | A2A Lite |
|------|------------|----------|
| Agent Card | Manual JSON file | Auto from `Agent(...)` |
| Skill Schemas | Manual per skill | Auto from type hints |
| Routing | Explicit registry | Decorator-based |
| Validation | Manual | From type hints |
| Error Handling | Explicit formatting | Auto-converted |
| Testing | HTTP client | TestClient built-in |

---

## 🔍 Key Differences from Google SDK

### 1. Skill Registration

**Google SDK:**
```python
# 3 files, manual registry
SKILL_REGISTRY = {
    "add": add,
    "subtract": subtract,
    # ...
}

# Manual routing logic
skill_func = SKILL_REGISTRY[skill_name]
result = skill_func(**params)
```

**A2A Lite:**
```python
# Just use decorator
@agent.skill("add")
async def add(a: float, b: float) -> dict:
    ...
# Routing is automatic!
```

### 2. Input Validation

**Google SDK:**
```python
# Manual validation in each skill
def add(a: float, b: float):
    if not isinstance(a, (int, float)):
        raise SkillError("Expected number")
    # ...
```

**A2A Lite:**
```python
# Type hints become validation
@agent.skill("add")
async def add(a: float, b: float) -> dict:
    # a and b are guaranteed to be floats
    ...
```

### 3. Testing

**Google SDK:**
```python
# Start server, use HTTP
subprocess.Popen(["python", "main.py"])
time.sleep(2)  # Wait for startup
response = httpx.post("http://localhost:8788/", json=payload)
```

**A2A Lite:**
```python
# Direct testing, no HTTP
client = AgentTestClient(agent)
result = client.call("add", a=10, b=5)
assert result == {"result": 15}
```

---

## 🎯 Advanced Features Demonstrated

### 1. Error Handling

A2A Lite automatically converts exceptions to A2A errors:

```python
@agent.skill("divide")
async def divide(a: float, b: float) -> dict:
    if b == 0:
        raise ValueError("Division by zero")
    return {"result": a / b}

# Client receives proper JSON-RPC error
# No manual error formatting needed!
```

### 2. Auto-Generated Schemas

Visit `http://localhost:8788/.well-known/agent.json` to see:

```json
{
  "skills": [
    {
      "name": "add",
      "inputSchema": {
        "type": "object",
        "properties": {
          "a": {"type": "number"},
          "b": {"type": "number"}
        },
        "required": ["a", "b"]
      }
    }
  ]
}
```

Generated automatically from `async def add(a: float, b: float)`!

### 3. Built-in TestClient

```python
from a2a_lite import AgentTestClient

client = AgentTestClient(agent)

# Test skills
result = client.call("add", a=10, b=5)
assert result.data["result"] == 15

# Test errors
try:
    client.call("divide", a=10, b=0)
except Exception as e:
    assert "zero" in str(e)

# List skills
skills = client.list_skills()
assert "add" in skills

# Get agent card
card = client.get_agent_card()
assert card["name"] == "Calculator"
```

---

## 📊 Complete Comparison

| Metric | Google SDK | A2A Lite | Savings |
|--------|------------|----------|---------|
| **Files** | 5 | 3 | 40% |
| **Lines of Code** | ~223 | ~67 | 70% |
| **Setup Time** | 30 min | 5 min | 83% |
| **Test Complexity** | HTTP + server | Direct | - |
| **Schema Maintenance** | Manual | Auto | - |

---

## 🚀 Next Steps

- Compare with [Google SDK version](../02_calculator_google/)
- Try [File Handling](../03_file_handling_lite/) for binary data
- Explore [Authentication](../05_auth_lite/) for secure agents
