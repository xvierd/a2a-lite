/**
 * Persistence Lite — pluggable TaskStore + PushNotifier example.
 *
 * Demonstrates:
 *   1. Passing an explicit InMemoryTaskStore as protocolTaskStore so the SDK's
 *      request handler uses YOUR store instead of creating its own.
 *   2. Selecting LogPushNotifier (dev) or WebhookPushNotifier (prod) based on
 *      environment variables.
 *   3. Two skills: a fast `echo` and a slow `slowSum` with a deliberate delay.
 *
 * Run (dev):
 *   npx tsx examples/typescript/10_persistence_lite/agent.ts
 *
 * Run (production webhook):
 *   WEBHOOK_URL=https://your.server/hook \
 *   WEBHOOK_SECRET=my-signing-secret \
 *   npx tsx examples/typescript/10_persistence_lite/agent.ts
 */

import { Agent, InMemoryTaskStore, LogPushNotifier, WebhookPushNotifier } from 'a2a-lite';
import type { PushNotifier } from 'a2a-lite';
import { InMemoryTaskStore as SdkTaskStore } from '@a2a-js/sdk/server';

// ---------------------------------------------------------------------------
// 1. Task store — shared instance you own and can inspect at runtime
// ---------------------------------------------------------------------------

// This is the lite TaskStore used for TaskContext injection within skills.
const liteStore = new InMemoryTaskStore();

// This is the SDK-level TaskStore used by the A2A protocol layer (request
// deduplication, task lifecycle).  By passing it explicitly you can swap it
// for a Redis or Postgres-backed implementation without changing anything else.
const protocolStore = new SdkTaskStore();

// ---------------------------------------------------------------------------
// 2. Push notifier — dev vs. production
// ---------------------------------------------------------------------------

function buildPushNotifier(): PushNotifier {
  const webhookUrl = process.env.WEBHOOK_URL;

  if (webhookUrl) {
    const secret = process.env.WEBHOOK_SECRET;
    console.log(`[config] Using WebhookPushNotifier → ${webhookUrl}${secret ? ' (signed)' : ''}`);
    return new WebhookPushNotifier({
      url: webhookUrl,
      secret,
      maxRetries: 3, // exponential back-off is built in
      timeoutMs: 10_000,
    });
  }

  console.log('[config] Using LogPushNotifier (set WEBHOOK_URL to switch to webhook mode)');
  return new LogPushNotifier();
}

// ---------------------------------------------------------------------------
// 3. Agent
// ---------------------------------------------------------------------------

const agent = new Agent({
  name: 'PersistenceLiteAgent',
  description: 'Demonstrates pluggable TaskStore and PushNotifier',
  version: '1.0.0',

  // Lite TaskStore — enables TaskContext in skills
  taskStore: liteStore,

  // Protocol TaskStore — passed to the SDK's DefaultRequestHandler
  protocolTaskStore: protocolStore,

  // Push notifier — fires after every skill completion
  pushNotifier: buildPushNotifier(),
});

// ---------------------------------------------------------------------------
// 4. Skills
// ---------------------------------------------------------------------------

/**
 * echo — fast, returns immediately.
 *
 * Call: { "skill": "echo", "params": { "message": "hello" } }
 */
agent.skill('echo', { description: 'Echo a message back' }, async (params) => {
  const { message } = params as { message: string };
  return { echoed: message, at: new Date().toISOString() };
});

/**
 * slowSum — adds two numbers after a deliberate delay.
 * This makes it easy to observe push notifications arriving after a pause.
 *
 * Call: { "skill": "slowSum", "params": { "a": 3, "b": 4, "delayMs": 2000 } }
 */
agent.skill(
  'slowSum',
  { description: 'Add two numbers after a delay (demonstrates async push notification)' },
  async (params) => {
    const { a, b, delayMs = 1000 } = params as { a: number; b: number; delayMs?: number };
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    return { sum: Number(a) + Number(b), delayMs };
  }
);

// ---------------------------------------------------------------------------
// 5. Startup hook — log store contents when the agent stops
// ---------------------------------------------------------------------------

agent.onShutdown(() => {
  const tasks = liteStore.list();
  if (tasks.length > 0) {
    console.log(`\n[shutdown] ${tasks.length} task(s) in lite store at exit:`);
    for (const t of tasks) {
      console.log(`  • ${t.id} [${t.skill}] → ${t.status.state}`);
    }
  }
});

// ---------------------------------------------------------------------------
// 6. Run
// ---------------------------------------------------------------------------

agent.run({ port: 8790 });
