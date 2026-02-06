/**
 * Webhooks and push notifications.
 *
 * Run: npx ts-node examples/10_webhooks.ts
 */
import { Agent } from '../src';

const agent = new Agent({ name: 'WebhookDemo', description: 'Shows webhooks' });

agent.onComplete((skill, result) => {
  console.log('✅ Skill "' + skill + '" completed: ' + JSON.stringify(result));
});

agent.skill('long_task', { description: 'Task that takes time' }, async ({ duration = 2, callback_url }: { duration?: number; callback_url?: string }) => {
  console.log('Starting task (' + duration + 's)...');
  await new Promise(resolve => setTimeout(resolve, duration * 1000));
  const result = { status: 'completed', duration };
  if (callback_url) {
    try {
      await fetch(callback_url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(result),
      });
    } catch (e) { console.error('Webhook failed'); }
  }
  return result;
});

agent.skill('process_with_progress', { description: 'Task with progress' }, async ({ items = 10, callback_url }: { items?: number; callback_url?: string }) => {
  for (let i = 0; i < items; i++) {
    await new Promise(resolve => setTimeout(resolve, 500));
    if (callback_url) {
      try {
        await fetch(callback_url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ progress: (i + 1) / items }),
        });
      } catch {}
    }
  }
  return { processed: items, status: 'done' };
});

agent.run({ port: 8787 });
