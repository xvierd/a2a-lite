# A2A Lite — TypeScript

[![npm](https://img.shields.io/npm/v/a2a-lite?label=npm&logo=npm&logoColor=white)](https://www.npmjs.com/package/a2a-lite)
[![GitHub](https://img.shields.io/badge/GitHub-a2a--lite-blue?logo=github)](https://github.com/xvierd/a2a-lite)

> **A2A Lite is designed for learning and prototyping.** It's the friendly on-ramp to Google's A2A Protocol — get familiar with agent-to-agent concepts with minimal boilerplate before diving into the full [google/a2a-js](https://github.com/a2aproject/a2a-js) SDK. Perfect for courses, POCs, and demos.

**Build A2A agents in 8 lines. Add features when you need them.**

Wraps the official [@a2a-js/sdk](https://github.com/a2aproject/a2a-js) with a simple, intuitive API. 100% protocol-compatible.

> **v1.0.1 — A2A Protocol v1.0.** Serves A2A v1.0 on `@a2a-js/sdk 1.0.1`.
> - **Transports:** JSON-RPC + REST (HTTP+JSON) via `agent.run()`; card at `/.well-known/agent-card.json`.
> - **gRPC:** not implemented in TypeScript yet (Python has experimental `run_grpc`; see root Feature Matrix).
> - Requires **Node.js >= 20**. No v0.3 compatibility.
> - Experimental **signed Agent Cards** via `signAgentCard` / `verifyAgentCard`.
> - See [MIGRATION.md](../../MIGRATION.md).

```typescript
import { Agent } from 'a2a-lite';

const agent = new Agent({ name: 'Bot', description: 'My bot' });

agent.skill('greet', async ({ name }: { name: string }) =>
  `Hello, ${name}!`
);

agent.run();
```

---

## Installation

```bash
npm install a2a-lite
```

**Requirements:** Node.js >= 20

---

## Quick Start

### 1. Create an agent

```typescript
import { Agent } from 'a2a-lite';

const agent = new Agent({
  name: 'Calculator',
  description: 'Does math'
});

agent.skill('add', async ({ a, b }: { a: number; b: number }) =>
  a + b
);

agent.skill('multiply', async ({ a, b }: { a: number; b: number }) =>
  a * b
);

agent.run(); // Listening on http://localhost:8787
```

### 2. Test it (no HTTP needed)

```typescript
import { AgentTestClient } from 'a2a-lite';

const client = new AgentTestClient(agent);
const result = await client.call('add', { a: 2, b: 3 });
expect(result).toBe(5);
```

---

## Features

### Skills

```typescript
agent.skill('greet', async ({ name }: { name: string }) =>
  `Hello, ${name}!`
);

// With description and tags
agent.skill('greet', async ({ name }) => `Hello, ${name}!`, {
  description: 'Greet someone by name',
  tags: ['greeting']
});
```

### Streaming

Use `async function*` to stream responses:

```typescript
agent.skill('chat', async function* ({ message }) {
  for (const word of message.split(' ')) {
    yield word + ' ';
  }
}, { streaming: true });
```

### Middleware

Cross-cutting concerns without touching skill code:

```typescript
agent.use(async (ctx, next) => {
  console.log(`Calling: ${ctx.skill}`);
  const result = await next();
  console.log(`Result: ${result}`);
  return result;
});
```

### Authentication

API keys are hashed in memory using SHA-256 — plaintext keys are never stored.

```typescript
import { Agent, APIKeyAuth, BearerAuth } from 'a2a-lite';

// API Key
const agent = new Agent({
  name: 'SecureBot',
  description: 'A secure bot',
  auth: new APIKeyAuth({ keys: new Set(['secret-key']) }),
});

// Bearer token with custom validator
const agent2 = new Agent({
  name: 'JWTBot',
  description: 'JWT-protected bot',
  auth: new BearerAuth({
    validator: async (token) => valid(token) ? 'user-id' : null
  }),
});
```

### File Handling

Accept files and return rich artifacts:

```typescript
import { FilePart, Artifact } from 'a2a-lite';

agent.skill('analyze', async ({ file }: { file: FilePart }) => {
  const content = await file.readText();
  return { name: file.name, size: content.length };
});
```

### Lifecycle Hooks

```typescript
agent.onStartup(() => console.log('Agent starting'));
agent.onShutdown(() => console.log('Agent stopping'));
agent.onComplete((skill, result) => console.log(`Completed: ${skill}`));
agent.onError((e) => ({ error: e.message }));
```

---

## Testing

`AgentTestClient` lets you test without starting an HTTP server:

```typescript
import { AgentTestClient } from 'a2a-lite';

const client = new AgentTestClient(agent);

// Regular call
const result = await client.call('greet', { name: 'World' });
expect(result).toBe('Hello, World!');

// Streaming (collects all chunks)
const results = await client.stream('chat', { message: 'hello world' });
expect(results.length).toBe(2);

// Inspect the agent
const skills = client.listSkills();
const card = client.getAgentCard();
```

`AgentTestClient` returns a `TestResult` with `.data`, `.text`, and `.json()`.

---

## Agent Constructor

```typescript
const agent = new Agent({
  name: 'Bot',              // Required
  description: '...',       // Required
  version: '1.0.0',         // Optional, default "1.0.0"
  url: undefined,           // Optional, auto-detected
  auth: undefined,          // Optional: APIKeyAuth, BearerAuth
  corsOrigins: ['...'],     // Optional: CORS allowed origins
});
```

## Run Options

```typescript
agent.run({
  host: '0.0.0.0',          // Default
  port: 8787,               // Default
});
```

---

## Multi-Agent Communication

### TaskHandle -- track remote tasks

When delegating to a remote agent, you can get back a `TaskHandle` that includes the A2A task ID alongside the result. This is useful for polling or cancelling long-running tasks.

```typescript
import { Agent, AgentNetwork, TaskHandle, getRemoteTask, cancelRemoteTask } from 'a2a-lite';

const network = new AgentNetwork();
network.add('data', 'http://localhost:8787');

const agent = new Agent({ name: 'Orchestrator', network });

agent.skill('process', async ({ query }: { query: string }) => {
  // Get a TaskHandle instead of just the result
  const handle = await agent.delegate('data', 'fetch', { query }, { returnHandle: true }) as TaskHandle;
  console.log(`Task ID: ${handle.taskId}`);
  console.log(`Agent: ${handle.agentUrl}`);
  console.log(`Result: ${handle.result}`);
  return String(handle.result);
});
```

#### Task Lifecycle -- poll and cancel remote tasks

Use convenience methods directly on the handle, or via the network by name:

```typescript
// Poll status directly on the handle
const status = await handle.getStatus();
const status2 = await handle.getStatus(15);  // custom timeout in seconds

// Or poll via network name
const status3 = await network.getTask('data', handle.taskId);
const status4 = await network.getTask('data', handle.taskId, 15);

// Cancel directly on the handle
await handle.cancel();
await handle.cancel(15);

// Or cancel via network name
await network.cancelTask('data', handle.taskId);
await network.cancelTask('data', handle.taskId, 15);
```

Low-level functions are also available:

```typescript
const status = await getRemoteTask('http://localhost:8787', taskId);
await cancelRemoteTask('http://localhost:8787', taskId);
```

### Client-Side SSE Streaming

When calling a remote streaming agent, consume its chunks as they arrive:

```typescript
import { streamRemoteSkill } from 'a2a-lite';

// Via agent.delegate with stream: true
agent.skill('display', async ({ topic }: { topic: string }) => {
  const chunks: string[] = [];
  const stream = agent.delegate('story', 'tellStory', { topic }, { stream: true }) as AsyncGenerator<string>;
  for await (const chunk of await stream) {
    process.stdout.write(chunk);
    chunks.push(chunk);
  }
  return chunks.join('');
});

// Or directly
for await (const chunk of streamRemoteSkill('http://localhost:8787', 'tellStory', { topic: 'dragons' })) {
  process.stdout.write(chunk);
}
```

### Agent Card Discovery

Fetch a remote agent's card to inspect its capabilities before delegating:

```typescript
import { discoverAgent, AgentCardInfo } from 'a2a-lite';

const card: AgentCardInfo = await discoverAgent('http://localhost:8787');
console.log(`Agent: ${card.name} v${card.version}`);
console.log(`Skills: ${card.skills.map(s => s.name).join(', ')}`);
console.log(`Streaming: ${card.supportsStreaming}`);

// Auto-discover when registering
network.add('data', 'http://localhost:8787', { autoDiscover: true });

// Validate skill exists before delegating
const result = await agent.delegate('data', 'fetch', { query: 'hello' }, { discover: true });
```

### Per-Task Push Notifications

```typescript
import { setTaskPushNotification } from 'a2a-lite';

const handle = await agent.delegate('worker', 'process', { data: '...' }, { returnHandle: true }) as TaskHandle;

// Register webhook for this specific task
await handle.subscribe('https://my-app.com/webhook', 'secret-token');

// Or directly
await setTaskPushNotification('http://localhost:8787', handle.taskId, 'https://my-app.com/webhook');

// Retrieve / remove
const config = await handle.getPushConfig();
await handle.unsubscribe();
```

---

## CLI

```bash
npx a2a-lite --help
npx a2a-lite init my-agent
npx a2a-lite inspect http://localhost:8787
npx a2a-lite info http://localhost:8787
npx a2a-lite test http://localhost:8787 greet --param name=World
npx a2a-lite discover http://localhost:8787 http://localhost:8788
npx a2a-lite doctor
npx a2a-lite doctor http://localhost:8787
```

| Command | Purpose |
|---------|---------|
| `init <name>` | Scaffold a TypeScript agent project |
| `inspect <url>` | Agent card and skills |
| `info <url>` | Compact plain-text info |
| `test <url> <skill> [--param k=v]` | Call a skill over A2A v1.0 |
| `discover <url...>` | Compare several agents |
| `doctor [url]` | Local env + optional remote v1.0 check |

Python has additional commands (`create`, `serve`); see [packages/python/docs/cli.md](../python/docs/cli.md).
---

## A2A Protocol Mapping

Everything maps directly to the underlying protocol — no magic, no lock-in.

| A2A Lite | A2A Protocol |
|----------|--------------|
| `agent.skill()` | Agent Skills |
| `agent.run()` | JSON-RPC + REST (HTTP+JSON) server |
| `{ streaming: true }` | SSE / `SendStreamingMessage` |
| `FilePart` | A2A File parts |
| `DataPart` | A2A Data parts |
| `Artifact` | A2A Artifacts |
| `APIKeyAuth` / `BearerAuth` / `OAuth2Auth` | `securitySchemes` on the agent card |
| `signAgentCard` / `verifyAgentCard` | Signed Agent Cards (**experimental**) |
| `AgentNetwork` / `delegate()` | Remote `SendMessage` |
| `TaskHandle` | Task ID + result wrapper |
| `AgentCardInfo` | Agent card metadata |
| `discoverAgent()` | `GET /.well-known/agent-card.json` |
| `getRemoteTask()` | `GetTask` JSON-RPC |
| `cancelRemoteTask()` | `CancelTask` JSON-RPC |
| `streamRemoteSkill()` | Client-side SSE consumer |

Wire methods use **A2A v1.0** names (`SendMessage`, not `message/send`) and the `A2A-Version: 1.0` header.

Full multi-language API: [AGENT.md](../../AGENT.md). CLI deep dive (Python has `create` / `serve`): [packages/python/docs/cli.md](../python/docs/cli.md).

---

## Full API Reference

See [AGENT.md](../../AGENT.md) for the complete multi-language API reference.

---

## License

MIT
