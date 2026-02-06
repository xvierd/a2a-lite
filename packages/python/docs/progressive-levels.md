# Progressive Levels

A2A Lite is designed around progressive disclosure. Start simple and add features as you need them.

## Level 1: Hello World

The simplest possible agent — 8 lines of code.

```python
from a2a_lite import Agent

agent = Agent(name="Bot", description="A simple bot")

@agent.skill("greet")
async def greet(name: str) -> str:
    return f"Hello, {name}!"

agent.run()
```

## Level 2: Multiple Skills

Add more skills to handle different tasks.

```python
agent = Agent(name="Calculator", description="Math operations")

@agent.skill("add", description="Add two numbers")
async def add(a: float, b: float) -> float:
    return a + b

@agent.skill("multiply", description="Multiply two numbers")
async def multiply(a: float, b: float) -> float:
    return a * b

agent.run()
```

## Level 3: Pydantic Validation

Use Pydantic models for automatic input validation.

```python
from pydantic import BaseModel

class User(BaseModel):
    name: str
    email: str
    age: int

@agent.skill("create_user")
async def create_user(user: User) -> dict:
    return {"created": user.name, "email": user.email}
```

## Level 4: Streaming

Yield results as they're generated.

```python
@agent.skill("count", streaming=True)
async def count(limit: int):
    for i in range(limit):
        yield f"Count: {i+1}"
```

## Level 5: Middleware

Add cross-cutting concerns like logging and rate limiting.

```python
from a2a_lite import logging_middleware, timing_middleware

agent.add_middleware(logging_middleware())
agent.add_middleware(timing_middleware())

@agent.middleware
async def custom_middleware(ctx, next):
    print(f"Calling: {ctx.skill}")
    result = await next()
    print(f"Done: {ctx.skill}")
    return result
```

## Level 6: Authentication

Protect your agent with API keys or OAuth2.

```python
from a2a_lite.auth import APIKeyAuth

agent = Agent(
    name="SecureBot",
    description="Protected agent",
    auth=APIKeyAuth(keys=["secret-key-123"]),
)
```

## Level 7: Task Tracking

Track progress for long-running operations.

```python
from a2a_lite import TaskContext

agent = Agent(name="Bot", description="...", task_store="memory")

@agent.skill("process")
async def process(data: str, task: TaskContext) -> str:
    await task.update("working", "Starting...", progress=0.0)
    # ... do work ...
    await task.update("working", "Almost done", progress=0.9)
    return "Done!"
```

## Level 8: Multi-Agent Orchestration

Delegate tasks across a network of agents.

```python
from a2a_lite.orchestration import AgentNetwork

network = AgentNetwork()
network.add("weather", "http://weather-agent:8787")
network.add("hotels", "http://hotel-agent:8787")

agent = Agent(name="Planner", description="...", network=network)

@agent.skill("plan_trip")
async def plan_trip(destination: str):
    weather = await agent.delegate("weather", "forecast", city=destination)
    hotels = await agent.delegate("hotels", "search", city=destination)
    return {"weather": weather, "hotels": hotels}
```

## Beyond Level 8

Combine features as needed:

- **MCP Tools**: Call external tool servers from skills
- **LLM Integration**: Wrap skills with OpenAI/Anthropic calls
- **File Handling**: Process uploaded files with `FilePart`
- **Custom Auth**: Build your own auth provider
- **Error Handling**: Use structured error types for clear feedback

See the individual guides for each advanced feature.
