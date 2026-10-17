import { describe, it, expect, vi } from 'vitest';
import { TaskState, type Task } from '@a2a-js/sdk';
import { ServerCallContext, type AgentExecutionEvent, type TaskStore } from '@a2a-js/sdk/server';
import type pg from 'pg';
import { PostgresExecution } from '../src/postgres-execution.js';

describe('remote subscription snapshot boundary', () => {
  it('emits a terminal committed after the SDK snapshot and before the first poll', async () => {
    const task: Task = {
      id: 'task',
      contextId: 'context',
      status: { state: TaskState.TASK_STATE_COMPLETED, timestamp: new Date().toISOString(), message: undefined },
      history: [],
      artifacts: [],
      metadata: undefined,
    };
    let finishQuery!: (value: unknown) => void;
    const pool = {
      query: vi.fn(
        () =>
          new Promise((resolve) => {
            finishQuery = resolve;
          }),
      ),
    };
    const coordinator = new PostgresExecution(pool as unknown as pg.Pool, {} as TaskStore, 'test');
    const bus = coordinator.eventBusManager.getByTaskId('task', new ServerCallContext())!;
    const events: AgentExecutionEvent[] = [];
    const done = new Promise<void>((resolve) => bus.on('finished', resolve));
    bus.on('event', (event) => events.push(event));
    // The query sees the new terminal revision even though the HTTP snapshot was WORKING.
    finishQuery({ rows: [{ revision: 2, task_data: task }] });
    await done;
    expect(events.map((event) => event.kind)).toEqual(['task', 'statusUpdate']);
    expect(events[1]).toMatchObject({ data: { status: { state: TaskState.TASK_STATE_COMPLETED } } });
    expect(pool.query).toHaveBeenCalledOnce();
    await coordinator.close();
  });
});
