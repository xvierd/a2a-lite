# Calculator - A2A protocol v1.0 from scratch (Java)

> **Multi-skill calculator implementing the A2A v1.0 wire protocol by hand — no SDK.**

This example demonstrates a calculator agent with multiple arithmetic operations, hand-rolled against the A2A protocol v1.0 wire format using only Javalin + Jackson. For the official Java SDK approach, see `packages/java`.

---

## 📁 Files Overview

```
src/main/java/com/example/calculator/
├── CalculatorAgent.java      # Main application
├── CalculatorSkill.java      # Skill implementations
└── MessageHandler.java       # A2A message handling
```

**Total: ~190 lines across 3 Java files**

---

## 🚀 Quick Start

```bash
cd java/02_calculator_google
mvn clean package
mvn exec:java
```

Agent starts at `http://localhost:8788`

---

## 🧪 Testing

### Agent card (A2A v1.0 discovery)

```bash
curl http://localhost:8788/.well-known/agent-card.json
```

### Addition

```bash
curl -X POST http://localhost:8788/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendMessage",
    "id": "1",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "m1",
        "parts": [{"text": "{\"skill\": \"add\", \"params\": {\"a\": 10, \"b\": 5}}"}]
      }
    }
  }'
```

### Division by zero (error handling)

```bash
curl -X POST http://localhost:8788/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendMessage",
    "id": "2",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "m2",
        "parts": [{"text": "{\"skill\": \"divide\", \"params\": {\"a\": 10, \"b\": 0}}"}]
      }
    }
  }'
```

---

## 📖 Skills Available

- `add(a, b)` - Addition
- `subtract(a, b)` - Subtraction
- `multiply(a, b)` - Multiplication
- `divide(a, b)` - Division (with zero check)
- `power(base, exponent)` - Exponentiation

---

## 🔍 Comparison

| Metric | From scratch (this) | A2A Lite |
|--------|---------------------|----------|
| Files | 3 | 1 |
| Lines | ~190 | ~50 |
| Schemas | Manual | Auto |

See [A2A Lite version](../02_calculator_lite/) for comparison.
