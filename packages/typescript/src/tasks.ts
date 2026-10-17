/**
 * Task lifecycle management for A2A Lite.
 *
 * Optional - only import if you need task tracking.
 *
 * Example:
 *   import { TaskContext } from 'a2a-lite';
 *
 *   const agent = new Agent({ name: "Bot", taskStore: "memory" });
 *
 *   agent.skill("process", async ({ data, task }: { data: string; task: TaskContext }) => {
 *     await task.update("working", "Processing...", 0.5);
 *     // ... do work ...
 *     await task.complete("Done!");
 *     return { success: true };
 *   });
 */

import { randomUUID } from 'crypto';
import type { Task, TaskState, TaskStatus, TaskStore } from './types.js';

/** In-memory learning store; synchronous Map mutations are atomic in one JS isolate. */
export class InMemoryTaskStore implements TaskStore {
  private tasks: Map<string, Task> = new Map();

  create(skill: string, params: Record<string, unknown>): Task {
    const now = new Date();
    const task: Task = {
      id: randomUUID().replace(/-/g, ''),
      skill,
      params,
      status: {
        state: 'submitted',
        timestamp: now,
      },
      history: [],
      createdAt: now,
      updatedAt: now,
    };

    this.tasks.set(task.id, task);
    return task;
  }

  get(id: string): Task | undefined {
    return this.tasks.get(id);
  }

  update(task: Task): void {
    task.updatedAt = new Date();
    this.tasks.set(task.id, task);
  }

  delete(id: string): boolean {
    return this.tasks.delete(id);
  }

  list(options?: { skill?: string; state?: TaskState }): Task[] {
    let tasks = Array.from(this.tasks.values());

    if (options?.skill) {
      tasks = tasks.filter((t) => t.skill === options.skill);
    }

    if (options?.state) {
      tasks = tasks.filter((t) => t.status.state === options.state);
    }

    return tasks;
  }
}

/**
 * Task context for skill handlers.
 *
 * Provides a simple interface for updating task status and progress.
 */
export class TaskContext {
  private task: Task;
  private statusCallbacks: Array<(status: TaskStatus) => void> = [];

  constructor(
    task: Task,
    readonly signal: AbortSignal = new AbortController().signal,
    private readonly maxHistory = 256,
    private readonly lease?: import('./postgres-execution.js').ExecutionLease,
  ) {
    this.task = task;
  }

  get checkpointData(): unknown {
    return this.lease?.checkpointData;
  }

  async checkpoint(data: unknown): Promise<void> {
    this.signal.throwIfAborted();
    if (!this.lease) throw new Error('Checkpoints require a checkpoint-enabled skill and distributed execution');
    await this.lease.checkpoint(data);
  }

  get taskId(): string {
    return this.task.id;
  }

  get state(): TaskState {
    return this.task.status.state;
  }

  get params(): Record<string, unknown> {
    return this.task.params;
  }

  /**
   * Update task status.
   */
  async update(state: TaskState = 'working', message?: string, progress?: number): Promise<void> {
    this.signal.throwIfAborted();
    if (message && Buffer.byteLength(message) > 1048576) throw new Error('Task status message limit exceeded');
    if (['completed', 'failed', 'canceled'].includes(this.state)) return;
    // Save current status to history
    this.task.history.push({ ...this.task.status });
    if (this.task.history.length > this.maxHistory)
      this.task.history.splice(0, this.task.history.length - this.maxHistory);

    // Update status
    const newStatus: TaskStatus = {
      state,
      message,
      progress,
      timestamp: new Date(),
    };

    this.task.status = newStatus;
    this.task.updatedAt = new Date();

    // Notify callbacks
    for (const callback of this.statusCallbacks) {
      try {
        callback(newStatus);
      } catch (callbackError) {
        console.warn(`Status callback error for task '${this.task.id}':`, callbackError);
      }
    }
  }

  /**
   * Mark task as completed.
   */
  async complete(message?: string): Promise<void> {
    await this.update('completed', message, 1.0);
  }

  /**
   * Mark task as failed.
   */
  async fail(error: string): Promise<void> {
    await this.update('failed', error);
  }

  /**
   * Register a status change callback.
   */
  onStatusChange(callback: (status: TaskStatus) => void): void {
    this.statusCallbacks.push(callback);
  }
}
