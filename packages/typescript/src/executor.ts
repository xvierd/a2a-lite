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
import type { SkillDefinition, MiddlewareContext, Middleware, AuthProvider, TaskStore } from './types.js';
import { TaskContext } from './tasks.js';
import { MCPClient } from './mcp/index.js';
import { A2ALiteError, SkillNotFoundError } from './errors.js';
import type { TaskPushRegistry } from './push-notifications.js';

/** Tracks per-execution task state so error handling follows the v1.0 event rules. */
interface ExecutionState {
  taskStarted: boolean;
  taskId: string;
  contextId: string;
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
  private pushRegistry?: TaskPushRegistry;

  constructor(options: {
    skills: Map<string, SkillDefinition>;
    errorHandler?: (error: Error) => Promise<unknown>;
    middlewares?: Middleware[];
    onCompleteHooks?: Array<(skill: string, result: unknown) => Promise<void> | void>;
    authProvider?: AuthProvider;
    taskStore?: TaskStore;
    mcpServers?: string[];
    pushRegistry?: TaskPushRegistry;
  }) {
    this.skills = options.skills;
    this.errorHandler = options.errorHandler;
    this.middlewares = options.middlewares ?? [];
    this.onCompleteHooks = options.onCompleteHooks ?? [];
    this.authProvider = options.authProvider;
    this.taskStore = options.taskStore;
    this.mcpServers = options.mcpServers ?? [];
    this.pushRegistry = options.pushRegistry;

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
    };

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

      const result = await handler();

      // If result is not null and not already streamed, send it
      if (result !== null && result !== undefined) {
        const responseText = typeof result === 'object' ? JSON.stringify(result, null, 2) : String(result);

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

      // Fire per-task push notification if registered
      await this.fireTaskWebhook(requestContext.taskId, skillName ?? '', result);

      eventBus.finished();
    } catch (error) {
      await this.handleError(error as Error, eventBus, execState);
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

    // Inject TaskContext if needed
    if (skillDef.needsTaskContext && this.taskStore) {
      // Store original params (without TaskContext)
      const originalParams = { ...params };
      const task = this.taskStore.create(skillName, originalParams);
      const taskContext = new TaskContext(task);
      const paramName = skillDef.taskContextParam ?? 'task';
      params[paramName] = taskContext;
    }

    // Inject MCPClient if needed
    if (skillDef.needsMcp && this.mcpClient) {
      const paramName = skillDef.mcpParam ?? 'mcp';
      params[paramName] = this.mcpClient;
    }

    // Execute handler
    const handler = skillDef.handler;

    if (skillDef.isStreaming) {
      // A2A v1.0 strict event rules: the FIRST event must be the task,
      // then status updates per chunk, then a terminal status.
      const requestContext = metadata.requestContext as RequestContext | undefined;
      const task: Task = requestContext?.task ?? {
        id: execState.taskId,
        contextId: execState.contextId,
        status: {
          state: TaskState.TASK_STATE_SUBMITTED,
          message: undefined,
          timestamp: new Date().toISOString(),
        },
        artifacts: [],
        history: requestContext?.userMessage ? [requestContext.userMessage] : [],
        metadata: undefined,
      };

      eventBus.publish(AgentEvent.task(task));
      execState.taskStarted = true;

      const publishStatus = (state: TaskState, text?: string) => {
        eventBus.publish(
          AgentEvent.statusUpdate({
            taskId: task.id,
            contextId: task.contextId,
            status: {
              state,
              message: text !== undefined ? this.buildAgentTextMessage(text, task.contextId, task.id) : undefined,
              timestamp: new Date().toISOString(),
            },
            metadata: undefined,
          }),
        );
      };

      publishStatus(TaskState.TASK_STATE_WORKING);

      // Stream generator results
      const gen = handler(params) as AsyncGenerator<unknown>;

      for await (const chunk of gen) {
        const text = typeof chunk === 'string' ? chunk : String(chunk);
        publishStatus(TaskState.TASK_STATE_WORKING, text);
      }

      publishStatus(TaskState.TASK_STATE_COMPLETED);

      return null; // Already streamed
    } else {
      return await handler(params);
    }
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
   * Fire a per-task push notification webhook if one is registered.
   */
  private async fireTaskWebhook(taskId: string, skill: string, result: unknown): Promise<void> {
    const config = this.pushRegistry?.get(taskId);
    if (!config) return;

    const event = {
      task_id: taskId,
      skill,
      result,
      status: 'completed',
      timestamp: Date.now() / 1000,
    };

    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (config.token) headers['Authorization'] = `Bearer ${config.token}`;

    try {
      await fetch(config.url, {
        method: 'POST',
        headers,
        body: JSON.stringify(event),
      });
    } catch (e) {
      console.warn(`[A2A] Per-task push notification failed for task ${taskId}:`, e);
    }
  }

  /**
   * Handle cancellation requests.
   *
   * Publishes a single message acknowledging the cancellation (mirrors the
   * Python implementation). The SDK's request handler owns the task state
   * transition to `canceled` in the task store.
   */
  async cancelTask(taskId: string, eventBus: ExecutionEventBus): Promise<void> {
    eventBus.publish(
      AgentEvent.message(this.buildAgentTextMessage(JSON.stringify({ status: 'cancelled', taskId }), '')),
    );
    eventBus.finished();
  }
}
