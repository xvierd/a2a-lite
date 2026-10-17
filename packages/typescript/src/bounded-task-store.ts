import type { TaskStore, ServerCallContext } from '@a2a-js/sdk/server';
import type { Task } from '@a2a-js/sdk';

/** Enforce finite protocol snapshots before they enter memory or durable storage. */
export function boundedTaskStore(
  store: TaskStore,
  options: { maxHistory: number; maxBytes: number; maxTasks?: number },
): TaskStore {
  const admitted = new Set<string>();
  const key = (task: Task, context: ServerCallContext) =>
    JSON.stringify([context.tenant ?? '', context.user?.userName ?? '', task.id]);
  return {
    load: (id, context) => store.load(id, context),
    list: (params, context) => store.list(params, context),
    save: async (task, context) => {
      const snapshot = { ...task, history: task.history.slice(-options.maxHistory) };
      if (Buffer.byteLength(JSON.stringify(snapshot)) > options.maxBytes)
        throw new Error('Task snapshot limit exceeded');
      const scope = key(task, context);
      if (options.maxTasks && !admitted.has(scope) && admitted.size >= options.maxTasks)
        throw new Error('Stored task capacity unavailable');
      // Reserve capacity synchronously before yielding to a potentially asynchronous store.
      const reserved = !admitted.has(scope);
      if (options.maxTasks) admitted.add(scope);
      try {
        await store.save(snapshot, context);
      } catch (error) {
        if (reserved) admitted.delete(scope);
        throw error;
      }
    },
  };
}
