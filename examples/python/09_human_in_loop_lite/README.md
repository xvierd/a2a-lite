# Human-in-the-Loop - A2A Lite (Python)

> **Agents that pause for human confirmation before sensitive operations.**

This example demonstrates the two-phase confirmation pattern over the A2A protocol: a skill first returns a `confirmation_required` summary, and only executes when called again with `confirmed=true` - essential for sensitive operations.

---

## 📋 Complexity Level: **ADVANCED**

**Concepts Covered:**
- Two-phase confirmation (validate → confirm → execute)
- Cost breakdowns before execution
- Multiple-choice approval flows
- Irreversibility warnings

---

## 📁 Files Overview

| File | Purpose | Lines |
|------|---------|-------|
| `agent.py` | Human-in-the-loop agent | ~185 |
| `requirements.txt` | Dependencies | ~2 |

**Total: ~187 lines across 2 files**

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
# Step 1: Initiate purchase (returns confirmation_required)
curl -X POST http://localhost:8793/ \
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
        "parts": [{"text": "{\"skill\": \"purchase\", \"params\": {\"item\": \"Laptop\", \"price\": 999.99}}"}]
      }
    }
  }'

# Response: {"status": "confirmation_required", "action": "purchase",
#            "details": {"item": "Laptop", "price": 999.99}, ...}

# Step 2: Human confirms -> execute
curl -X POST http://localhost:8793/ \
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
        "parts": [{"text": "{\"skill\": \"purchase\", \"params\": {\"item\": \"Laptop\", \"price\": 999.99, \"confirmed\": true}}"}]
      }
    }
  }'

# Response: {"status": "completed", "order_id": "...", ...}
```

### Test 2: Document Approval (multiple choice)

```bash
# Step 1: no decision -> returns the available options
# {"skill": "approve_document", "params": {"doc_id": "doc-42"}}

# Step 2: apply a decision
# {"skill": "approve_document", "params": {"doc_id": "doc-42",
#   "decision": "revise", "feedback": "Needs a better abstract"}}
```

---

## 📖 Key Concepts

### 1. The Two-Phase Pattern

```python
@agent.skill("purchase")
async def purchase(item: str, price: float, confirmed: bool = False) -> dict:
    if not confirmed:
        # Phase 1: present the details for human review
        return {
            "status": "confirmation_required",
            "details": {"item": item, "price": price},
        }

    # Phase 2: the human confirmed - execute
    return {"status": "completed", "order_id": "...", "item": item}
```

### 2. Why Not Mid-Execution Questions?

A2A Lite has no mid-execution question API. The two-phase pattern is
stateless and works over plain `SendMessage`: every decision point is a
new call carrying the confirmation as a parameter. The client (or an
orchestrating agent) owns the review step.

---

## 📊 Comparison

| Aspect | Manual Implementation | A2A Lite (two-phase) |
|--------|----------------------|----------------------|
| **Validation** | Custom code | Skill params + defaults |
| **Confirmation Flow** | Custom state machine | `confirmed` parameter |
| **Protocol** | Custom endpoints | Standard `SendMessage` |
| **Lines of Code** | ~400+ | ~185 |
