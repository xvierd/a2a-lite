# Human-in-the-Loop - A2A Lite (Python)

> **Agents that pause for human input and confirmation.**

This example demonstrates how A2A Lite simplifies building agents that can pause execution to ask for human input, confirmations, or decisions - essential for sensitive operations.

---

## 📋 Complexity Level: **ADVANCED**

**Concepts Covered:**
- Pausing tasks for human input
- Asking questions mid-execution
- Confirmation dialogs
- Multiple choice selection
- State persistence during wait

---

## 📁 Files Overview

| File | Purpose | Lines |
|------|---------|-------|
| `agent.py` | Human-in-the-loop agent | ~100 |
| `requirements.txt` | Dependencies | ~2 |
| `test_human_loop.py` | Tests | ~40 |

**Total: ~142 lines across 3 files**

---

## 🚀 Quick Start

```bash
cd python/09_human_in_loop_lite
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python agent.py
```

---

## 🧪 Testing Human-in-the-Loop

### Test 1: Purchase with Confirmation

```bash
# Step 1: Initiate purchase (returns question)
curl -X POST http://localhost:8793/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "1",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "{\"skill\": \"purchase\", \"params\": {\"item\": \"Laptop\", \"price\": 999.99}}"}]
      }
    }
  }'

# Response: {"status": "waiting", "question": "Confirm purchase of Laptop for $999.99?"}

# Step 2: Confirm (resume task)
curl -X POST http://localhost:8793/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "2",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "{\"skill\": \"respond\", \"params\": {\"task_id\": \"<task-id>\", \"response\": \"yes\"}}"}]
      }
    }
  }'
```

---

## 📖 Key Concepts

### 1. Using InteractionContext

```python
from a2a_lite import InteractionContext

@agent.skill("sensitive_operation")
async def sensitive_operation(confirm: bool = False, ctx: InteractionContext = None):
    if not confirm:
        # Ask for confirmation
        response = await ctx.ask(
            question="Are you sure?",
            options=["yes", "no"]
        )
        confirm = response == "yes"
    
    if confirm:
        return execute_operation()
```

### 2. Task State Persistence

A2A Lite automatically:
- Saves task state when waiting
- Resumes from same point
- Maintains context across requests

---

## 📊 Comparison

| Aspect | Manual Implementation | A2A Lite |
|--------|----------------------|----------|
| **State Management** | Custom DB/code | Automatic |
| **Task Resumption** | Complex routing | `await ctx.ask()` |
| **Context Preservation** | Manual | Built-in |
| **Lines of Code** | ~400+ | ~100 |
