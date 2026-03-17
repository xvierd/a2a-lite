# Hello World - A2A Lite (Python)

> **Simplified A2A agent using A2A Lite - 8 lines of code!**

This example demonstrates the same "Hello Agent" functionality as the Google SDK version, but using A2A Lite's decorator-based API. Compare the two approaches to see how A2A Lite reduces boilerplate while maintaining full protocol compatibility.

---

## 📁 Files Overview

| File | Purpose | Lines |
|------|---------|-------|
| `agent.py` | Complete agent implementation | ~8 |
| `requirements.txt` | Dependencies | ~2 |
| `test_agent.py` | Unit tests (optional) | ~15 |

**Total: ~25 lines across 3 files**

Compare to Google SDK: **~93 lines across 4 files** → **73% less code!**

---

## 🏗️ Architecture

```
Client Request → A2A Lite → Your Function → A2A Response
                     ↓
            Auto-generated Agent Card
```

A2A Lite handles all the protocol details for you:
- ✅ Automatic agent card generation
- ✅ JSON-RPC parsing and formatting
- ✅ Skill routing
- ✅ Input validation from type hints
- ✅ Error handling

---

## 🚀 Setup and Run

### Step 1: Create Virtual Environment

```bash
cd python/01_hello_world_lite
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Run the Agent

```bash
python agent.py
```

The agent will start on `http://localhost:8787`

---

## 🧪 Testing the Agent

### Test 1: Get Agent Card (Discovery)

```bash
curl http://localhost:8787/.well-known/agent.json
```

**Expected Response:**
```json
{
  "name": "HelloAgent",
  "description": "A simple greeting agent using A2A Lite",
  "version": "1.0.0",
  "url": "http://localhost:8787/",
  "skills": [
    {
      "name": "greet",
      "description": "Greet someone by name",
      "inputSchema": {
        "properties": {
          "name": {"type": "string"}
        },
        "required": ["name"],
        "type": "object"
      },
      "outputSchema": {
        "type": "string"
      }
    }
  ]
}
```

**Note**: The schema is automatically generated from your Python type hints!

### Test 2: Call the Greet Skill

```bash
curl -X POST http://localhost:8787/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "1",
    "params": {
      "message": {
        "role": "user",
        "parts": [
          {
            "type": "text",
            "text": "{\"skill\": \"greet\", \"params\": {\"name\": \"World\"}}"
          }
        ],
        "messageId": "msg-1"
      }
    }
  }'
```

**Expected Response:**
```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "result": {
    "message": {
      "role": "agent",
      "parts": [
        {
          "type": "text",
          "text": "Hello, World!"
        }
      ]
    }
  }
}
```

### Test 3: Run Unit Tests (No HTTP Required!)

```bash
python test_agent.py
```

A2A Lite includes a `TestClient` that tests agents without starting an HTTP server:

```python
from a2a_lite import AgentTestClient

client = AgentTestClient(agent)
result = client.call("greet", name="World")
assert result == "Hello, World!"
```

---

## 📖 Code Explanation

### Complete Agent (`agent.py`)

```python
from a2a_lite import Agent

agent = Agent(
    name="HelloAgent",
    description="A simple greeting agent using A2A Lite"
)

@agent.skill("greet")
async def greet(name: str) -> str:
    return f"Hello, {name}!"

agent.run()
```

That's it! Let's break down what A2A Lite does for you:

### 1. Agent Creation

```python
agent = Agent(name="...", description="...")
```

- Creates an A2A-compliant agent
- Auto-generates agent card from type hints
- Sets up HTTP server internally

### 2. Skill Registration

```python
@agent.skill("greet")
async def greet(name: str) -> str:
    ...
```

- Registers the function as an A2A skill
- Auto-generates JSON Schema from type hints (`name: str` → `{"type": "string"}`)
- Handles routing automatically

### 3. Running the Agent

```python
agent.run()
```

- Starts the HTTP server on port 8787
- Serves agent card at `/.well-known/agent.json`
- Handles all A2A protocol messages

---

## 🔍 Comparison with Google SDK

| Aspect | Google SDK | A2A Lite |
|--------|------------|----------|
| **Files** | 4 files | 1 file |
| **Lines** | ~93 lines | ~8 lines |
| **Agent Card** | Manual JSON | Auto-generated |
| **Schemas** | Hand-written | From type hints |
| **Routing** | Explicit | Decorator-based |
| **Testing** | HTTP client | Built-in TestClient |

### Google SDK Version (for comparison):

```python
# main.py - ~90 lines
# agent_card.json - ~25 lines  
# skills.py - ~50 lines
# Total: Manual work required

@app.post("/")
async def handle_message(request: Request):
    body = await request.json()
    message = params.get("message", {})
    parts = message.get("parts", [])
    # ... manual parsing
    skill_call = json.loads(part.get("text", "{}"))
    skill_name = skill_call.get("skill")
    # ... manual routing
    result = execute_skill(skill_name, skill_params)
    # ... manual response formatting
```

### A2A Lite Version:

```python
@agent.skill("greet")
async def greet(name: str) -> str:
    return f"Hello, {name}!"
# Everything else is automatic!
```

---

## 🎯 Key Benefits of A2A Lite

### 1. **Progressive Complexity**
Start simple, add features as needed:

```python
# Level 1: Basic
@agent.skill("greet")
async def greet(name: str) -> str:
    return f"Hello, {name}!"

# Level 2: Pydantic models
from pydantic import BaseModel

class User(BaseModel):
    name: str
    email: str

@agent.skill("create_user")
async def create_user(user: User) -> dict:
    return {"id": 1, "name": user.name}

# Level 3: Middleware
@agent.middleware
async def log_calls(ctx, next):
    print(f"Calling: {ctx.skill}")
    return await next()
```

### 2. **Type Safety**
Type hints become runtime validation:

```python
@agent.skill("add")
async def add(a: int, b: int) -> int:
    return a + b

# A2A Lite automatically:
# - Validates 'a' and 'b' are integers
# - Generates JSON Schema for the skill
# - Converts inputs from JSON to Python types
```

### 3. **Built-in Testing**

```python
from a2a_lite import AgentTestClient

client = AgentTestClient(agent)

# Test without HTTP
result = client.call("greet", name="World")
assert result == "Hello, World!"

# Get agent card
card = client.get_agent_card()
assert "greet" in client.list_skills()
```

### 4. **100% Protocol Compatible**

A2A Lite wraps the official SDK - you can:
- ✅ Interoperate with Google SDK agents
- ✅ Use all A2A protocol features
- ✅ Migrate incrementally

---

## 📚 Learning Path

1. **Start here**: Understand this Hello World example
2. **Compare**: Look at the [Google SDK version](../01_hello_world_google/) to see what's abstracted
3. **Next**: Try the [Calculator example](../02_calculator_lite/) for multiple skills
4. **Advanced**: Explore [File Handling](../03_file_handling_lite/) or [Authentication](../05_auth_lite/)

---

## 🐛 Troubleshooting

**Port already in use:**
```python
agent.run(port=8788)  # Use different port
```

**Module not found:**
```bash
source venv/bin/activate
pip install -r requirements.txt
```

**Want to see debug logs:**
```python
agent.run(log_level="debug")
```

---

## 💡 Pro Tips

1. **Use async functions**: All skills should be `async def`
2. **Type hints matter**: They're used for validation and documentation
3. **Test early**: Use `AgentTestClient` for rapid iteration
4. **Read the agent card**: Visit `/.well-known/agent.json` to see auto-generated schemas
