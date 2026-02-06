# A2A Lite — TypeScript

[![npm](https://img.shields.io/npm/v/a2a-lite?label=npm&logo=npm&logoColor=white)](https://www.npmjs.com/package/a2a-lite)
[![GitHub](https://img.shields.io/badge/GitHub-a2a--lite-blue?logo=github)](https://github.com/xvierd/a2a-lite)

**Build A2A agents in 8 lines. Add features when you need them.**

Wraps the official [@a2a-js/sdk](https://github.com/a2aproject/a2a-js) with a simple, intuitive API. 100% protocol-compatible.

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

## A2A Protocol Mapping

Everything maps directly to the underlying protocol — no magic, no lock-in.

| A2A Lite | A2A Protocol |
|----------|--------------|
| `agent.skill()` | Agent Skills |
| `{ streaming: true }` | SSE Streaming |
| `FilePart` | A2A File parts |
| `DataPart` | A2A Data parts |
| `Artifact` | A2A Artifacts |
| `APIKeyAuth` / `BearerAuth` | Security schemes |

---

## Full API Reference

See [AGENT.md](../../AGENT.md) for the complete multi-language API reference.

---

## License

MIT
