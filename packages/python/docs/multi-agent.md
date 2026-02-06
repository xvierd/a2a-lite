# Multi-Agent Orchestration

A2A Lite provides `AgentNetwork` and `agent.delegate()` for coordinating multiple agents.

## Quick Start

### Simple Delegation

Call a remote agent directly by URL:

```python
result = await agent.delegate("http://weather-agent:8787", "forecast", city="NYC")
```

### Named Network

Register agents by name and delegate by name:

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

## AgentNetwork API

### `add(name, url)` / `remove(name)` / `get(name)`

Manage the agent registry:

```python
network = AgentNetwork()
network.add("weather", "http://weather:8787")
network.get("weather")    # "http://weather:8787"
network.remove("weather") # True
```

### `list()`

Get all registered agents:

```python
agents = network.list()
# {"weather": "http://weather:8787", "hotels": "http://hotel:8788"}
```

### `call(name, skill, **params)`

Call a specific agent's skill:

```python
result = await network.call("weather", "forecast", city="NYC")
```

### `broadcast(skill, **params)`

Call the same skill on all agents concurrently:

```python
results = await network.broadcast("health_check")
# {"weather": {"status": "ok"}, "hotels": {"status": "ok"}}
```

Errors from individual agents are captured (not raised):

```python
results = await network.broadcast("status")
# {"agent_a": "ok", "agent_b": {"error": "Connection refused", "type": "ConnectError"}}
```

## Agent.delegate()

`delegate()` is a convenience method on Agent that resolves names through the network:

```python
# With a URL (always works)
result = await agent.delegate("http://other:8787", "skill", x=1)

# With a name (requires network)
result = await agent.delegate("weather", "forecast", city="NYC")
```

It returns the **parsed result** (not the raw A2A envelope), so you get the actual data back.

## Example

See [`examples/14_multi_agent_network.py`](https://github.com/a2a-lite/a2a-lite/blob/main/packages/python/examples/14_multi_agent_network.py) for a complete multi-agent example with weather, hotel, and planner agents.
