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

### `add(name, url, *, client_config=None)` / `remove(name)` / `get(name)`

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

## Authenticated Peers and Task Handles

```python
from a2a_lite import AgentNetwork, ClientConfig

network = AgentNetwork()
network.add("worker", "https://worker.example", client_config=ClientConfig(
    headers={"X-API-Key": "your-key"},
    tenant="team-a",  # the server must authorize this tenant
))
# The remote skill must return a Task (task=True, TaskContext or streaming).
card = await network.discover("worker")
handle = await network.call("worker", "work", return_handle=True)
status = await handle.get_status()
```

`return_handle=True` accepts a Task with an `id` or a Message with an explicit `taskId`. A standalone Message without a task reference raises `ValueError` when a handle is requested. The handle retains the credentials and tenant used for its call. A sync/async `credential_provider(url)` can supply fresh headers for each request. Credentials remain scoped to the original origin unless `allowed_origins` explicitly permits another origin, and redirects are disabled. See the [deployment guide](production.md) for stable principals and key rotation.

With `auto_discover=True`, named operations wait for the card before sending. A discovery failure reaches the caller. To retry discovery explicitly, call `await network.discover(name)`. Discovery starts at the registered base URL. Calls and handles use the advertised JSON-RPC endpoint, including its path. When you configure a tenant, discovery prefers its matching interface and can also use an interface without an advertised tenant. Requests to the latter omit the tenant, including task and webhook operations. A direct call without discovery uses the manually configured tenant. A conflicting advertised tenant is rejected before invoking the skill. With no configured tenant, the first compatible interface supplies the tenant. For a standalone call after `card = await discover(base, client_config=config)`, pass `client_config=card.client_config(config)` when calling `card.url`.

## Structured streams and task subscriptions

`network.stream(name, skill, **params)` yields text. Use `stream_events` to keep each A2A event exactly as the peer sent it, including file and data parts, artifact IDs, metadata and optional chunk flags. The following example starts a streaming skill and reads its artifact parts.

```python
from contextlib import aclosing
from a2a_lite import RemoteAgentError

try:
    async with aclosing(network.stream_events("worker", "stream")) as events:
        async for event in events:
            if "artifactUpdate" in event:
                artifact = event["artifactUpdate"]["artifact"]
                print(artifact["artifactId"], artifact["parts"])
            elif "message" in event:
                print(event["message"]["parts"])
            elif "statusUpdate" in event:
                print(event["statusUpdate"]["status"]["state"])
            else:
                print(event["task"]["id"])
except RemoteAgentError as exc:
    print(exc, exc.code, exc.data)
```

`RemoteAgentError.code` and `.data` carry the remote JSON-RPC error when present. A mismatched response ID, malformed envelope or unexpected EOF also raises `RemoteAgentError`. Text already delivered stays available to the caller. The structured stream exposes a failed task's status and message. The text stream raises on that state.

To follow a task already running, use `network.subscribe_task("worker", task_id)` or `handle.events()`. The client checks that the first event contains the requested task and that each later update belongs to the same task ID. Use `aclosing` when you may leave the loop early. `handle.subscribe(webhook_url)` registers a webhook.

## Pagination and continuation

```python
token = None
while True:
    page = await network.list_tasks("worker", page_size=20, page_token=token)
    for task in page.get("tasks", []):
        print(task["id"], task["status"]["state"])
    token = page.get("nextPageToken")
    if not token:
        break

# An earlier call to review requested more input.
updated = await handle.continue_task("review", answer="approved")
print(updated.task_id, updated.context_id, updated.result)
```

`list_tasks` accepts the optional filters `context_id`, `status`, `history_length`, `status_timestamp_after` and `include_artifacts`. Repeat the same filters on subsequent pages and pass the opaque token unchanged. If you only have the task ID, `await network.continue_task("worker", task_id, "review", answer="approved")` reads its context and sends a fresh user message in the existing task. Supply `context_id=...` when you already have it.

## Google ADK and free text

A Google ADK `RemoteA2aAgent` can discover a Lite server through its public card URL. To route natural-language requests on an agent with multiple skills, set `free_text_skill="chat"` and register a skill named `chat` with a `message: str` parameter. Explicit skill selection continues to work through a text part such as `{"skill":"add","params":{"a":2,"b":3}}`. With several skills and no configured text entry, an unaddressed message returns a Message containing a JSON object with `type="SkillNotFoundError"` and `available_skills`. The caller can use those names to construct an explicit request. [Calculator example](../examples/02_calculator.py)

## Example

See [`examples/14_multi_agent_network.py`](https://github.com/xvierd/a2a-lite/blob/main/packages/python/examples/14_multi_agent_network.py) for a complete multi-agent example with weather, hotel, and planner agents.
