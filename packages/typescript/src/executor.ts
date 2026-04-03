/**
 * LiteAgentExecutor - Wraps skill handlers into the A2A SDK's AgentExecutor interface.
 *
 * This is the bridge between a2a-lite's simple skill registration and the
 * official @a2a-js/sdk's execution model.
 */

import type {
  AgentExecutor,
  RequestContext,
  ExecutionEventBus,
} from '@a2a-js/sdk/server';
import { v4 as uuidv4 } from 'uuid';
import type {
  SkillDefinition,
  MiddlewareContext,
  Middleware,
  AuthProvider,
  TaskStore,
} from './types.js';
import { TaskContext } from './tasks.js';
import { MCPClient } from './mcp/index.js';
import { A2ALiteError, SkillNotFoundError } from './errors.js';
import type { TaskPushRegistry } from './push-notifications.js';

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
   */
  async execute(
    requestContext: RequestContext,
    eventBus: ExecutionEventBus
  ): Promise<void> {
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
        metadata: { parts, eventBus, contextId: requestContext.contextId },
      };

      // Define final handler
      const finalHandler = async (): Promise<unknown> => {
        return await this.executeSkill(skillName, params, eventBus, ctx.metadata);
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
        const responseText =
          typeof result === 'object' ? JSON.stringify(result, null, 2) : String(result);

        const responseMessage = {
          kind: 'message' as const,
          messageId: uuidv4(),
          role: 'agent' as const,
          parts: [{ kind: 'text' as const, text: responseText }],
          contextId: requestContext.contextId,
        };

        eventBus.publish(responseMessage);
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
      await this.fireTaskWebhook(requestContext.contextId, skillName ?? '', result);

      eventBus.finished();
    } catch (error) {
      await this.handleError(error as Error, eventBus, requestContext);
    }
  }

  /**
   * Execute a skill with the given parameters.
   */
  private async executeSkill(
    skillName: string | null,
    params: Record<string, unknown>,
    eventBus: ExecutionEventBus,
    metadata: Record<string, unknown>
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
      // Stream generator results
      const gen = handler(params) as AsyncGenerator<unknown>;

      for await (const chunk of gen) {
        const text = typeof chunk === 'string' ? chunk : String(chunk);

        const message = {
          kind: 'message' as const,
          messageId: uuidv4(),
          role: 'agent' as const,
          parts: [{ kind: 'text' as const, text }],
          contextId: metadata.contextId as string,
        };

        eventBus.publish(message);
      }

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
        if ('kind' in part && part.kind === 'text' && 'text' in part) {
          text = part.text;
        } else if ('kind' in part && (part.kind === 'file' || part.kind === 'data')) {
          parts.push(part);
        }
      }
    }

    return { text, parts };
  }

  /**
   * Handle execution errors.
   */
  private async handleError(
    error: Error,
    eventBus: ExecutionEventBus,
    requestContext: RequestContext
  ): Promise<void> {
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

    const errorMessage = {
      kind: 'message' as const,
      messageId: uuidv4(),
      role: 'agent' as const,
      parts: [{ kind: 'text' as const, text: JSON.stringify(errorResult) }],
      contextId: requestContext.contextId,
    };

    eventBus.publish(errorMessage);
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
   */
  async cancelTask(): Promise<void> {
    // Cancellation is a no-op for simple skills
  }
}
