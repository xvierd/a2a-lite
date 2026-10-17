import { describe, expect, it } from 'vitest';
import { InMemoryTaskStore, ServerCallContext } from '@a2a-js/sdk/server';
import { TaskState, type Task } from '@a2a-js/sdk';
import { boundedTaskStore } from '../src/bounded-task-store.js';

const context = new ServerCallContext();
const task = (id: string): Task => ({
  id,
  contextId: 'context',
  status: { state: TaskState.TASK_STATE_WORKING, timestamp: new Date().toISOString(), message: undefined },
  history: [],
  artifacts: [],
  metadata: undefined,
});
describe('protocol store resource limits', () => {
  it('rejects new memory tasks at capacity while retaining updates to an admitted task', async () => {
    const store = boundedTaskStore(new InMemoryTaskStore(), { maxHistory: 2, maxBytes: 2048, maxTasks: 1 });
    await store.save(task('first'), context);
    await expect(store.save(task('second'), context)).rejects.toThrow('capacity');
    await store.save(
      { ...task('first'), status: { ...task('first').status!, state: TaskState.TASK_STATE_COMPLETED } },
      context,
    );
    expect((await store.load('first', context))!.status!.state).toBe(TaskState.TASK_STATE_COMPLETED);
  });
  it('bounds stored snapshot bytes before persistence', async () => {
    const store = boundedTaskStore(new InMemoryTaskStore(), { maxHistory: 2, maxBytes: 256 });
    await expect(store.save({ ...task('large'), metadata: { padding: 'x'.repeat(1024) } }, context)).rejects.toThrow(
      'snapshot',
    );
    expect(await store.load('large', context)).toBeUndefined();
  });
});
