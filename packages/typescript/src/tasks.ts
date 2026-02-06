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

/**
 * Lightweight async mutex for protecting shared state.
 */
class AsyncMutex {
  private queue: Array<() => void> = [];
  private locked = false;

  async acquire(): Promise<void> {
    if (!this.locked) {
      this.locked = true;
      return;
    }
    return new Promise<void>((resolve) => {
      this.queue.push(resolve);
    });
  }

  release(): void {
    const next = this.queue.shift();
    if (next) {
      next();
    } else {
      this.locked = false;
    }
  }

  async runExclusive<T>(fn: () => T | Promise<T>): Promise<T> {
    await this.acquire();
    try {
      return await fn();
    } finally {
      this.release();
    }
  }
}

/**
 * In-memory task store with mutex for thread safety.
 */
export class InMemoryTaskStore implements TaskStore {
  private tasks: Map<string, Task> = new Map();
  private mutex = new AsyncMutex();

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
    this.mutex.runExclusive(() => {
      task.updatedAt = new Date();
      this.tasks.set(task.id, task);
    });
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

  constructor(task: Task) {
    this.task = task;
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
  async update(
    state: TaskState = 'working',
    message?: string,
    progress?: number
  ): Promise<void> {
    // Save current status to history
    this.task.history.push({ ...this.task.status });

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
