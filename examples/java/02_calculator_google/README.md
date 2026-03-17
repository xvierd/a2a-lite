# Calculator - Google A2A SDK (Java)

> **Multi-skill calculator using Google's official A2A Java SDK.**

This example demonstrates a calculator agent with multiple arithmetic operations using the official Google A2A Java SDK.

---

## 📁 Files Overview

```
src/main/java/com/example/calculator/
├── CalculatorAgent.java      # Main application
├── CalculatorSkill.java      # Skill implementations
└── MessageHandler.java       # A2A message handling
```

**Total: ~180 lines across 3 Java files**

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
        "parts": [{"type": "text", "text": "{\"skill\": \"add\", \"params\": {\"a\": 10, \"b\": 5}}"}]
      }
    }
  }'

# Division by zero (error handling)
curl -X POST http://localhost:8788/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "2",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "{\"skill\": \"divide\", \"params\": {\"a\": 10, \"b\": 0}}"}]
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

| Metric | Google SDK | A2A Lite |
|--------|------------|----------|
| Files | 3 | 1 |
| Lines | ~180 | ~50 |
| Schemas | Manual | Auto |

See [A2A Lite version](../02_calculator_lite/) for comparison.
