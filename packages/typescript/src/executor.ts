/**
 * LiteAgentExecutor - Wraps skill handlers into the A2A SDK's AgentExecutor interface.
 *
 * This is the bridge between a2a-lite's simple skill registration and the
 * official @a2a-js/sdk's execution model.
 */

import { AgentEvent, type AgentExecutor, type RequestContext, type ExecutionEventBus } from '@a2a-js/sdk/server';
import { Role, TaskState } from '@a2a-js/sdk';
import type { Message, Part, Task } from '@a2a-js/sdk';
import { v4 as uuidv4 } from 'uuid';
import type {
  SkillDefinition,
  MiddlewareContext,
  Middleware,
  AuthProvider,
  TaskStore,
  Task as LiteTask,
  TaskStatus,
} from './types.js';
import { TaskContext } from './tasks.js';
import { CANCEL_OBSERVER, type DistributedExecution, type ExecutionLease } from './postgres-execution.js';
import { MCPClient } from './mcp/index.js';
import { A2ALiteError, SkillNotFoundError } from './errors.js';

/** Tracks per-execution task state so error handling follows the v1.0 event rules. */
interface ExecutionState {
  taskStarted: boolean;
  taskId: string;
  contextId: string;
  terminal?: boolean;
  controller: AbortController;
  localTask?: LiteTask;
  lease?: ExecutionLease;
  requestContext: RequestContext;
  events: number;
  outputBytes: number;
}

export class LiteAgentExecutor implements AgentExecutor {
  private skills: Map<string, SkillDefinition>;
  private errorHandler?: (error: Error) => Promise<unknown>;
  private middlewares: Middleware[];
  private onCompleteHooks: Array<(skill: string, result: unknown) => Promise<void> | void>;
  private authProvider?: AuthProvider;
  private taskStore?: TaskStore;
  private mcpServers: string[];
  private mcpClient?: MCPClient;
  private executions = new Map<ExecutionEventBus, ExecutionState>();
  private activeHandlers = 0;
  private executionTimeoutMs: number;
  private maxExecutions: number;
  private maxTaskHistory: number;
  private executionCoordinator?: DistributedExecution;
  private maxEvents: number;
  private maxOutputBytes: number;
  private waitForTerminal?: (id: string, context: RequestContext) => Promise<void>;

  constructor(options: {
    skills: Map<string, SkillDefinition>;
    errorHandler?: (error: Error) => Promise<unknown>;
    middlewares?: Middleware[];
    onCompleteHooks?: Array<(skill: string, result: unknown) => Promise<void> | void>;
    authProvider?: AuthProvider;
    taskStore?: TaskStore;
    mcpServers?: string[];
    executionTimeoutMs?: number;
    maxExecutions?: number;
    maxTaskHistory?: number;
    executionCoordinator?: DistributedExecution;
    maxEventsPerExecution?: number;
    maxOutputBytes?: number;
    waitForTerminal?: (id: string, context: RequestContext) => Promise<void>;
  }) {
    this.maxEvents = options.maxEventsPerExecution ?? 4096;
    this.maxOutputBytes = options.maxOutputBytes ?? 1048576;
    this.waitForTerminal = options.waitForTerminal;
    this.executionCoordinator = options.executionCoordinator;
    this.executionTimeoutMs = options.executionTimeoutMs ?? 60000;
    this.maxExecutions = options.maxExecutions ?? 128;
    this.maxTaskHistory = options.maxTaskHistory ?? 256;
    this.skills = options.skills;
    this.errorHandler = options.errorHandler;
    this.middlewares = options.middlewares ?? [];
    this.onCompleteHooks = options.onCompleteHooks ?? [];
    this.authProvider = options.authProvider;
    this.taskStore = options.taskStore;
    this.mcpServers = options.mcpServers ?? [];

    // Create MCP client if servers are configured
    if (this.mcpServers.length > 0) {
      this.mcpClient = new MCPClient(this.mcpServers);
    }
  }

  /**
   * Execute a skill based on the incoming request.
   * This is called by the SDK's request handler.
   *
   * A2A v1.0 event rules: the FIRST event published must be a task or a
   * message. Non-streaming skills publish a single message; streaming skills
   * publish the task first, then status updates per chunk, then completion.
   */
  async execute(requestContext: RequestContext, eventBus: ExecutionEventBus): Promise<void> {
    const execState: ExecutionState = {
      taskStarted: false,
      taskId: requestContext.taskId,
      contextId: requestContext.contextId,
      controller: new AbortController(),
      requestContext,
      events: 0,
      outputBytes: 0,
    };
    this.executions.set(eventBus, execState);

    try {
      // Extract message and parts from request
      const { text, parts } = this.extractMessageAndParts(requestContext);

      // Parse skill call
      const { skill: skillName, params } = this.parseMessage(text);

      // Build middleware context
      const ctx: MiddlewareContext = {
        skill: skillName ?? '',
        params,
        message: text,
        metadata: { parts, eventBus, contextId: requestContext.contextId, requestContext },
      };

      // Define final handler
      const finalHandler = async (): Promise<unknown> => {
        return await this.executeSkill(skillName, params, eventBus, ctx.metadata, execState);
      };

      // Execute through middleware chain
      let handler = finalHandler;
      for (let i = this.middlewares.length - 1; i >= 0; i--) {
        const middleware = this.middlewares[i];
        const next = handler;
        handler = async () => middleware(ctx, next);
      }

      if (this.activeHandlers >= this.maxExecutions) throw new Error('Agent execution capacity unavailable');
      this.activeHandlers++;
      const pending = Promise.resolve()
        .then(handler)
        .finally(() => {
          this.activeHandlers--;
        });
      const signal = execState.controller.signal;
      let onAbort!: () => void;
      const aborted = new Promise<never>((_resolve, reject) => {
        onAbort = () => reject(signal.reason);
        signal.addEventListener('abort', onAbort, { once: true });
      });
      const timer = setTimeout(
        () => execState.controller.abort(new Error('Task execution deadline exceeded')),
        this.executionTimeoutMs,
      );
      timer.unref();
      let result: unknown;
      try {
        result = await Promise.race([pending, aborted]);
      } finally {
        clearTimeout(timer);
        signal.removeEventListener('abort', onAbort);
      }

      // If result is not null and not already streamed, send it
      if (!execState.taskStarted && result !== null && result !== undefined) {
        const responseText = typeof result === 'object' ? JSON.stringify(result, null, 2) : String(result);

        this.checkBudget(execState, responseText);
        eventBus.publish(AgentEvent.message(this.buildAgentTextMessage(responseText, requestContext.contextId)));
      }

      // Call completion hooks
      for (const hook of this.onCompleteHooks) {
        try {
          await hook(skillName ?? '', result);
        } catch (hookError) {
          console.warn(`Completion hook error for skill '${skillName ?? ''}':`, hookError);
        }
      }

      eventBus.finished();
    } catch (error) {
      if (!execState.terminal) await this.handleError(error as Error, eventBus, execState);
    } finally {
      this.executions.delete(eventBus);
      if (!execState.taskStarted) await execState.lease?.release();
    }
  }

  /**
   * Build an A2A v1.0 agent text message.
   */
  private buildAgentTextMessage(text: string, contextId: string, taskId = ''): Message {
    return {
      messageId: uuidv4(),
      contextId,
      taskId,
      role: Role.ROLE_AGENT,
      parts: [this.textPart(text)],
      metadata: undefined,
      extensions: [],
      referenceTaskIds: [],
    };
  }

  /**
   * Build an A2A v1.0 text part.
   */
  private textPart(text: string): Part {
    return {
      content: { $case: 'text', value: text },
      metadata: undefined,
      filename: '',
      mediaType: '',
    };
  }

  /**
   * Execute a skill with the given parameters.
   */
  private async executeSkill(
    skillName: string | null,
    params: Record<string, unknown>,
    eventBus: ExecutionEventBus,
    metadata: Record<string, unknown>,
    execState: ExecutionState,
  ): Promise<unknown> {
    // Default to first skill only if there's exactly one
    if (!skillName) {
      if (this.skills.size === 0) {
        throw new SkillNotFoundError('', []);
      }
      if (this.skills.size === 1) {
        skillName = this.skills.keys().next().value!;
      } else {
        throw new SkillNotFoundError('', Array.from(this.skills.keys()));
      }
    }

    const skillDef = this.skills.get(skillName);
    if (!skillDef) {
      throw new SkillNotFoundError(skillName, Array.from(this.skills.keys()));
    }

    const requestContext = metadata.requestContext as RequestContext | undefined;
    if (skillDef.taskMode || skillDef.isStreaming || skillDef.needsTaskContext) {
      if (this.executionCoordinator) {
        execState.lease = await this.executionCoordinator.acquire(execState.taskId, execState.requestContext.context);
        execState.requestContext.context.state.set(CANCEL_OBSERVER, () => {
          const reason = new Error('Task canceled');
          reason.name = 'TaskCanceledError';
          if (!execState.terminal && execState.taskStarted) {
            this.publishStatus(eventBus, execState, TaskState.TASK_STATE_CANCELED);
            eventBus.finished();
          }
          execState.controller.abort(reason);
        });
        execState.lease.signal.addEventListener(
          'abort',
          () => {
            const reason = execState.lease!.signal.reason;
            if (reason instanceof Error && reason.name === 'TaskCanceledError' && execState.taskStarted) {
              this.publishStatus(eventBus, execState, TaskState.TASK_STATE_CANCELED);
              eventBus.finished();
            }
            execState.controller.abort(reason);
          },
          { once: true },
        );
      }

      const submitted = {
        state: TaskState.TASK_STATE_SUBMITTED,
        message: undefined,
        timestamp: new Date().toISOString(),
      };
      // A resumed INPUT_REQUIRED snapshot must not release the newly acquired lease.
      const task: Task = requestContext?.task
        ? { ...requestContext.task, status: submitted }
        : {
            id: execState.taskId,
            contextId: execState.contextId,
            status: { state: TaskState.TASK_STATE_SUBMITTED, message: undefined, timestamp: new Date().toISOString() },
            artifacts: [],
            history: requestContext?.userMessage ? [requestContext.userMessage] : [],
            metadata: undefined,
          };
      eventBus.publish(AgentEvent.task(task));
      execState.taskStarted = true;
      const now = new Date();
      const localTask: LiteTask = {
        id: task.id,
        skill: skillName,
        params: { ...params },
        status: { state: 'submitted', timestamp: now },
        history: [],
        createdAt: now,
        updatedAt: now,
      };
      execState.localTask = localTask;
      this.taskStore?.update(localTask);
      if (skillDef.needsTaskContext) {
        const taskContext = new TaskContext(
          localTask,
          execState.controller.signal,
          this.maxTaskHistory,
          skillDef.checkpoint ? execState.lease : undefined,
        );
        taskContext.onStatusChange((status) => {
          this.taskStore?.update(localTask);
          // Finish only after handler result/error, so artifacts precede terminal events.
          if (!['completed', 'failed', 'canceled', 'input-required'].includes(status.state)) {
            this.publishStatus(eventBus, execState, this.protocolState(status.state), status.message, status.progress);
          }
        });
        params[skillDef.taskContextParam ?? 'task'] = taskContext;
      }
    }
    if (skillDef.needsMcp && this.mcpClient) params[skillDef.mcpParam ?? 'mcp'] = this.mcpClient;

    if (skillDef.isStreaming) {
      this.publishStatus(eventBus, execState, TaskState.TASK_STATE_WORKING);
      for await (const chunk of skillDef.handler(params) as AsyncGenerator<unknown>) {
        execState.controller.signal.throwIfAborted();
        this.publishStatus(
          eventBus,
          execState,
          TaskState.TASK_STATE_WORKING,
          typeof chunk === 'string' ? chunk : String(chunk),
        );
      }
      if (!execState.terminal) this.publishStatus(eventBus, execState, TaskState.TASK_STATE_COMPLETED);
      return null;
    }
    const result = await skillDef.handler(params);
    execState.controller.signal.throwIfAborted();
    if (execState.taskStarted) {
      const text =
        result === undefined ? undefined : typeof result === 'object' ? JSON.stringify(result) : String(result);
      if (text !== undefined) {
        this.checkBudget(execState, text);
        eventBus.publish(
          AgentEvent.artifactUpdate({
            taskId: execState.taskId,
            contextId: execState.contextId,
            artifact: {
              artifactId: uuidv4(),
              name: 'result',
              description: '',
              parts: [this.textPart(text)],
              metadata: undefined,
              extensions: [],
            },
            append: false,
            lastChunk: true,
            metadata: undefined,
          }),
        );
      }
      const status = execState.localTask?.status;
      this.publishStatus(
        eventBus,
        execState,
        status?.state === 'failed' || status?.state === 'canceled' || status?.state === 'input-required'
          ? this.protocolState(status.state)
          : TaskState.TASK_STATE_COMPLETED,
        status?.state === 'failed' ? status.message : text,
      );
    }
    return result;
  }

  private checkBudget(state: ExecutionState, text: string): void {
    state.events++;
    state.outputBytes += Buffer.byteLength(text, 'utf8');
    if (state.events > this.maxEvents || state.outputBytes > this.maxOutputBytes)
      throw new Error('Task output limit exceeded');
  }

  private protocolState(state: TaskStatus['state']): TaskState {
    return {
      submitted: TaskState.TASK_STATE_SUBMITTED,
      working: TaskState.TASK_STATE_WORKING,
      'input-required': TaskState.TASK_STATE_INPUT_REQUIRED,
      completed: TaskState.TASK_STATE_COMPLETED,
      failed: TaskState.TASK_STATE_FAILED,
      canceled: TaskState.TASK_STATE_CANCELED,
    }[state];
  }

  private publishStatus(
    bus: ExecutionEventBus,
    state: ExecutionState,
    status: TaskState,
    text?: string,
    progress?: number,
  ): void {
    if (state.terminal) return;
    if (status !== TaskState.TASK_STATE_CANCELED) this.checkBudget(state, text ?? '');
    state.terminal = [
      TaskState.TASK_STATE_COMPLETED,
      TaskState.TASK_STATE_FAILED,
      TaskState.TASK_STATE_CANCELED,
    ].includes(status);
    bus.publish(
      AgentEvent.statusUpdate({
        taskId: state.taskId,
        contextId: state.contextId,
        status: {
          state: status,
          message: text !== undefined ? this.buildAgentTextMessage(text, state.contextId, state.taskId) : undefined,
          timestamp: new Date().toISOString(),
        },
        metadata: progress === undefined ? undefined : { progress },
      }),
    );
  }

  /**
   * Parse message to extract skill name and params.
   */
  private parseMessage(message: string): { skill: string | null; params: Record<string, unknown> } {
    try {
      const data = JSON.parse(message);
      if (typeof data === 'object' && data !== null && 'skill' in data) {
        return { skill: data.skill, params: data.params ?? {} };
      }
    } catch {
      // Not JSON
    }
    return { skill: null, params: { message } };
  }

  /**
   * Extract message text and any file/data parts from request context.
   * A2A v1.0 parts carry their content in a oneof: `content.$case`.
   */
  private extractMessageAndParts(context: RequestContext): {
    text: string;
    parts: unknown[];
  } {
    let text = '';
    const parts: unknown[] = [];

    const message = context.userMessage;
    if (message?.parts) {
      for (const part of message.parts) {
        const content = part.content;
        if (content?.$case === 'text') {
          text = content.value;
        } else if (content?.$case === 'raw' || content?.$case === 'url' || content?.$case === 'data') {
          parts.push(part);
        }
      }
    }

    return { text, parts };
  }

  /**
   * Handle execution errors.
   *
   * If a task was already started (streaming skill), the error is published
   * as a failed status update; otherwise as a single message (the first —
   * and only — event).
   */
  private async handleError(error: Error, eventBus: ExecutionEventBus, execState: ExecutionState): Promise<void> {
    let errorResult: unknown;

    if (error instanceof A2ALiteError) {
      errorResult = error.toResponse();
    } else if (this.errorHandler) {
      try {
        errorResult = await this.errorHandler(error);
      } catch (handlerError) {
        errorResult = {
          error: error.message,
          handlerError: (handlerError as Error).message,
          type: error.name,
        };
      }
    } else {
      errorResult = {
        error: error.message,
        type: error.name,
      };
    }

    const errorText = JSON.stringify(errorResult);

    if (execState.taskStarted) {
      eventBus.publish(
        AgentEvent.statusUpdate({
          taskId: execState.taskId,
          contextId: execState.contextId,
          status: {
            state: TaskState.TASK_STATE_FAILED,
            message: this.buildAgentTextMessage(errorText, execState.contextId, execState.taskId),
            timestamp: new Date().toISOString(),
          },
          metadata: undefined,
        }),
      );
    } else {
      eventBus.publish(AgentEvent.message(this.buildAgentTextMessage(errorText, execState.contextId)));
    }
    eventBus.finished();
  }

  /**
   * Handle cancellation requests.
   *
   * Publishes a single message acknowledging the cancellation (mirrors the
   * Python implementation). The SDK's request handler owns the task state
   * transition to `canceled` in the task store.
   */
  async cancelTask(taskId: string, eventBus: ExecutionEventBus): Promise<void> {
    const state = this.executions.get(eventBus);
    if (!state || state.taskId !== taskId) return;
    state.controller.abort(new Error('Task canceled'));
    this.publishStatus(eventBus, state, TaskState.TASK_STATE_CANCELED);
    eventBus.finished();
  }

  async close(): Promise<void> {
    const pending = [...this.executions.entries()];
    for (const [bus, state] of pending) await this.cancelTask(state.taskId, bus);
    await Promise.all(
      pending
        .filter(([, state]) => state.taskStarted)
        .map(([, state]) => this.waitForTerminal?.(state.taskId, state.requestContext)),
    );
    await this.mcpClient?.close();
  }
}
