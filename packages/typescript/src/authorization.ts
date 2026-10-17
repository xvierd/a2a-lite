import type { A2ARequestHandler, ServerCallContext } from '@a2a-js/sdk/server';
import { TaskNotFoundError } from '@a2a-js/sdk/errors';
import { PERSISTED_CANCEL } from './postgres-execution.js';
import type { Task, StreamResponse } from '@a2a-js/sdk';
import type { AuthResult } from './types.js';

export const AUTH_RESULT = 'a2a-lite.auth';
const PRINCIPAL_PREFIX = 'a2a:v1:';

/** Shared cross-language scope encoding; ordinary legacy IDs remain unchanged. */
export function principalKey(userId: string, namespace?: string): string {
  if (namespace === undefined && !userId.startsWith(PRINCIPAL_PREFIX)) return userId;
  return PRINCIPAL_PREFIX + Buffer.from(JSON.stringify([namespace ?? null, userId])).toString('base64url');
}

function authorize(context: ServerCallContext): void {
  const auth = context.state.get(AUTH_RESULT) as AuthResult | undefined;
  const tenant = context.tenant ?? '';
  const tenants = auth?.anonymous ? [''] : (auth?.authorizedTenants ?? ['']);
  if (!auth?.authenticated || !Array.from(tenants).includes(tenant)) throw new TaskNotFoundError();
}

/** The transport sets the requested tenant before invoking these operations. */
export function authorizedHandler(
  handler: A2ARequestHandler,
  execution?: import('./postgres-execution.js').DistributedExecution,
): A2ARequestHandler {
  function checked<T>(context: ServerCallContext, operation: () => T): T {
    authorize(context);
    return operation();
  }
  return {
    getAgentCard: () => handler.getAgentCard(),
    getAuthenticatedExtendedAgentCard: (p, c) => checked(c, () => handler.getAuthenticatedExtendedAgentCard(p, c)),
    sendMessage: (p, c) =>
      checked(c, async () => {
        const result = await handler.sendMessage(p, c);
        const canceled = c.state.get(PERSISTED_CANCEL) as Task | undefined;
        return canceled ?? result;
      }),
    sendMessageStream: (p, c) => checked(c, () => reconcileStream(handler.sendMessageStream(p, c), c)),
    getTask: (p, c) => checked(c, () => handler.getTask(p, c)),
    listTasks: (p, c) => checked(c, () => handler.listTasks(p, c)),
    cancelTask: (p, c) => checked(c, () => (execution ? execution.cancelTask(p.id, c) : handler.cancelTask(p, c))),
    resubscribe: (p, c) => checked(c, () => handler.resubscribe(p, c)),
    createTaskPushNotificationConfig: (p, c) => checked(c, () => handler.createTaskPushNotificationConfig(p, c)),
    getTaskPushNotificationConfig: (p, c) => checked(c, () => handler.getTaskPushNotificationConfig(p, c)),
    listTaskPushNotificationConfigs: (p, c) => checked(c, () => handler.listTaskPushNotificationConfigs(p, c)),
    deleteTaskPushNotificationConfig: (p, c) => checked(c, () => handler.deleteTaskPushNotificationConfig(p, c)),
  };
}

/** Replace queued local output with a cancellation already committed by another replica. */
async function* reconcileStream(
  source: AsyncGenerator<StreamResponse>,
  context: ServerCallContext,
): AsyncGenerator<StreamResponse> {
  for await (const event of source) {
    const canceled = context.state.get(PERSISTED_CANCEL) as Task | undefined;
    if (canceled) {
      yield {
        payload: {
          $case: 'statusUpdate',
          value: { taskId: canceled.id, contextId: canceled.contextId, status: canceled.status, metadata: undefined },
        },
      };
      return;
    }
    yield event;
  }
}
