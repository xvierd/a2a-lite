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

export class LiteAgentExecutor implements AgentExecutor {
  private skills: Map<string, SkillDefinition>;
  private errorHandler?: (error: Error) => Promise<unknown>;
  private middlewares: Middleware[];
  private onCompleteHooks: Array<(skill: string, result: unknown) => Promise<void> | void>;
  private authProvider?: AuthProvider;
  private taskStore?: TaskStore;
  private mcpServers: string[];
  private mcpClient?: MCPClient;

  constructor(options: {
    skills: Map<string, SkillDefinition>;
    errorHandler?: (error: Error) => Promise<unknown>;
    middlewares?: Middleware[];
    onCompleteHooks?: Array<(skill: string, result: unknown) => Promise<void> | void>;
    authProvider?: AuthProvider;
    taskStore?: TaskStore;
    mcpServers?: string[];
  }) {
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
        return { error: 'No skills registered' };
      }
      if (this.skills.size === 1) {
        skillName = this.skills.keys().next().value!;
      } else {
        return {
          error: 'No skill specified. Use {"skill": "name", "params": {...}} format.',
          availableSkills: Array.from(this.skills.keys()),
        };
      }
    }

    const skillDef = this.skills.get(skillName);
    if (!skillDef) {
      return {
        error: `Unknown skill: ${skillName}`,
        availableSkills: Array.from(this.skills.keys()),
      };
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

    if (this.errorHandler) {
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
   * Handle cancellation requests.
   */
  async cancelTask(): Promise<void> {
    // Cancellation is a no-op for simple skills
  }
}
