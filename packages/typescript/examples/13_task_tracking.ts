/**
 * Task lifecycle and progress tracking.
 *
 * Run: npx ts-node examples/13_task_tracking.ts
 */
import { Agent } from '../src';

const agent = new Agent({ name: 'TaskTracker', description: 'Shows task progress' });

agent.skill('long_process', { description: 'Long task with progress', streaming: true }, async function* ({ steps }: { steps: number }) {
  yield { status: 'working', message: 'Starting...', progress: 0 };
  for (let i = 0; i < steps; i++) {
    await new Promise(resolve => setTimeout(resolve, 500));
    yield { status: 'working', message: 'Step ' + (i + 1) + '/' + steps, progress: (i + 1) / steps };
  }
  yield { status: 'completed', steps_completed: steps };
});

agent.skill('batch_import', { description: 'Import with progress', streaming: true }, async function* ({ items }: { items: string[] }) {
  const total = items.length;
  let successful = 0, failed = 0;
  yield { status: 'working', message: 'Importing ' + total + ' items...', progress: 0 };
  for (let i = 0; i < total; i++) {
    try {
      await new Promise(resolve => setTimeout(resolve, 100));
      successful++;
    } catch { failed++; }
    yield { status: 'working', message: 'Imported ' + (i + 1) + '/' + total, progress: (i + 1) / total };
  }
  yield { total, successful, failed };
});

agent.run({ port: 8787 });
