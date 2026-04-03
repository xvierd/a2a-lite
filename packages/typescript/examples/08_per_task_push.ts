/**
 * Per-task push notifications.
 *
 * This example shows how a caller can register a webhook for a specific
 * task ID so the server fires the webhook when that task completes.
 *
 * Run:
 *   npx ts-node examples/08_per_task_push.ts
 *
 * Architecture:
 *   1. A WorkerAgent listens on port 8787 with a "process" skill.
 *   2. Client code delegates with returnHandle: true, getting a TaskHandle.
 *   3. The client calls handle.subscribe('http://localhost:9000/webhook')
 *      to register a per-task webhook.
 *   4. When the task completes, the server POSTs an event to the webhook URL.
 */
import { Agent } from '../src';

// ---------------------------------------------------------------------------
// 1. Create a worker agent with a "process" skill
// ---------------------------------------------------------------------------

const worker = new Agent({
  name: 'WorkerAgent',
  description: 'Processes data and fires per-task push notifications',
});

worker.skill(
  'process',
  { description: 'Simulate a data-processing task' },
  async ({ data }: { data: string }) => {
    // Simulate work
    await new Promise((resolve) => setTimeout(resolve, 1000));
    return { processed: data.toUpperCase(), timestamp: Date.now() };
  },
);

// Start the worker on port 8787
worker.run({ port: 8787 });

// ---------------------------------------------------------------------------
// 2. Client code (would normally be in a separate process)
// ---------------------------------------------------------------------------

async function clientDemo() {
  // Wait for the server to start
  await new Promise((resolve) => setTimeout(resolve, 500));

  // Delegate a task and get a handle back
  const secondAgent = new Agent({ name: 'Client', description: 'Client agent' });
  const handle = await secondAgent.delegate(
    'http://localhost:8787/a2a/jsonrpc',
    'process',
    { data: 'hello world' },
    { returnHandle: true },
  );

  if (!handle || typeof handle !== 'object' || !('taskId' in handle)) {
    console.error('Expected a TaskHandle');
    return;
  }

  const taskHandle = handle as import('../src/orchestration').TaskHandle;
  console.log(`Task created: ${taskHandle.taskId}`);

  // Register a per-task push notification webhook
  // In production, this URL would point to your own callback server.
  await taskHandle.subscribe('http://localhost:9000/webhook', 'my-secret-token');
  console.log('Subscribed to push notifications for task', taskHandle.taskId);

  // Verify the subscription
  const config = await taskHandle.getPushConfig();
  console.log('Push config:', config);

  // Unsubscribe when no longer needed
  // await taskHandle.unsubscribe();
}

clientDemo().catch(console.error);
