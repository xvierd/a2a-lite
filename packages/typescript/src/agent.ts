/**
 * Core Agent class - the heart of A2A Lite.
 *
 * Wraps the official @a2a-js/sdk with a simple, intuitive API.
 *
 * Simple:
 *   const agent = new Agent({ name: "Bot", description: "My bot" });
 *
 *   agent.skill("greet", async ({ name }: { name: string }) => {
 *     return `Hello, ${name}!`;
 *   });
 *
 *   agent.run();
 */

import express, { Express } from 'express';
import {
  DefaultRequestHandler,
  InMemoryTaskStore,
} from '@a2a-js/sdk/server';
import {
  agentCardHandler,
  jsonRpcHandler,
  UserBuilder,
} from '@a2a-js/sdk/server/express';
import type { AgentCard, AgentSkill, AgentCapabilities } from '@a2a-js/sdk';

import { LiteAgentExecutor } from './executor.js';
import type {
  AgentConfig,
  SkillConfig,
  SkillDefinition,
  SkillHandler,
  Middleware,
  TaskStore,
} from './types.js';
import { InMemoryTaskStore as LiteTaskStore } from './tasks.js';
import { NoAuth } from './auth.js';

export class Agent {
  readonly name: string;
  readonly description: string;
  readonly version: string;
  readonly url?: string;

  private skills: Map<string, SkillDefinition> = new Map();
  private middlewares: Middleware[] = [];
  private errorHandler?: (error: Error) => Promise<unknown>;
  private onStartupHooks: Array<() => Promise<void> | void> = [];
  private onShutdownHooks: Array<() => Promise<void> | void> = [];
  private onCompleteHooks: Array<(skill: string, result: unknown) => Promise<void> | void> = [];
  private taskStore?: TaskStore;
  private auth: { authenticate: Function; getScheme: Function };
  private hasStreaming = false;
  private corsOrigins?: string[];
  private production: boolean;

  constructor(config: AgentConfig) {
    this.name = config.name;
    this.description = config.description;
    this.version = config.version ?? '1.0.0';
    this.url = config.url;
    this.corsOrigins = config.corsOrigins;
    this.production = config.production ?? false;

    // Setup task store
    if (config.taskStore === 'memory') {
      this.taskStore = new LiteTaskStore();
    } else if (config.taskStore) {
      this.taskStore = config.taskStore;
    }

    // Setup auth
    this.auth = config.auth ?? new NoAuth();
  }

  /**
   * Register a skill.
   *
   * Simple:
   *   agent.skill("greet", async ({ name }) => `Hello, ${name}!`);
   *
   * With options:
   *   agent.skill("chat", { streaming: true }, async function* ({ message }) {
   *     for (const word of message.split(' ')) {
   *       yield word;
   *     }
   *   });
   */
  skill(name: string, handler: SkillHandler): this;
  skill(name: string, config: SkillConfig, handler: SkillHandler): this;
  skill(
    name: string,
    configOrHandler: SkillConfig | SkillHandler,
    maybeHandler?: SkillHandler
  ): this {
    let config: SkillConfig;
    let handler: SkillHandler;

    if (typeof configOrHandler === 'function') {
      config = {};
      handler = configOrHandler;
    } else {
      config = configOrHandler;
      handler = maybeHandler!;
    }

    const skillName = config.name ?? name;
    const isStreaming = config.streaming ?? this.isGeneratorFunction(handler);

    if (isStreaming) {
      this.hasStreaming = true;
    }

    // Auto-detect TaskContext parameter by analyzing the handler
    const taskContextInfo = this.detectTaskContextParameter(handler);
    const needsTaskContext = config.taskContext ?? taskContextInfo.needsTaskContext;
    const taskContextParam = taskContextInfo.paramName;

    const needsInteraction = config.interaction ?? false;

    const skillDef: SkillDefinition = {
      name: skillName,
      description: config.description ?? `Skill: ${skillName}`,
      tags: config.tags ?? [],
      handler,
      inputSchema: {},
      outputSchema: {},
      isStreaming,
      needsTaskContext,
      needsInteraction,
      taskContextParam,
    };

    this.skills.set(skillName, skillDef);
    return this;
  }

  /**
   * Add middleware.
   *
   *   agent.use(async (ctx, next) => {
   *     console.log(`Calling: ${ctx.skill}`);
   *     return await next();
   *   });
   */
  use(middleware: Middleware): this {
    this.middlewares.push(middleware);
    return this;
  }

  /**
   * Set error handler.
   */
  onError(handler: (error: Error) => Promise<unknown>): this {
    this.errorHandler = handler;
    return this;
  }

  /**
   * Add startup hook.
   */
  onStartup(hook: () => Promise<void> | void): this {
    this.onStartupHooks.push(hook);
    return this;
  }

  /**
   * Add shutdown hook.
   */
  onShutdown(hook: () => Promise<void> | void): this {
    this.onShutdownHooks.push(hook);
    return this;
  }

  /**
   * Add completion hook.
   */
  onComplete(hook: (skill: string, result: unknown) => Promise<void> | void): this {
    this.onCompleteHooks.push(hook);
    return this;
  }

  /**
   * Build the A2A-compliant Agent Card.
   */
  buildAgentCard(host = 'localhost', port = 8787): AgentCard {
    const skills: AgentSkill[] = Array.from(this.skills.values()).map((s) => ({
      id: s.name,
      name: s.name,
      description: s.description,
      tags: s.tags,
    }));

    const url = this.url ?? `http://${host}:${port}`;

    const capabilities: AgentCapabilities = {
      streaming: this.hasStreaming,
      pushNotifications: this.onCompleteHooks.length > 0,
    };

    return {
      name: this.name,
      description: this.description,
      protocolVersion: '0.3.0',
      version: this.version,
      url: `${url}/a2a/jsonrpc`,
      capabilities,
      defaultInputModes: ['text'],
      defaultOutputModes: ['text'],
      skills,
    };
  }

  /**
   * Build the Express app using the official SDK handlers.
   */
  buildApp(): Express {
    const app = express();

    // Create the executor that bridges to our skills
    const executor = new LiteAgentExecutor({
      skills: this.skills,
      errorHandler: this.errorHandler,
      middlewares: this.middlewares,
      onCompleteHooks: this.onCompleteHooks,
      authProvider: this.auth as any,
      taskStore: this.taskStore,
    });

    // Create the SDK's request handler
    const agentCard = this.buildAgentCard();
    const requestHandler = new DefaultRequestHandler(
      agentCard,
      new InMemoryTaskStore(),
      executor
    );

    // Mount SDK handlers
    app.use(
      '/.well-known/agent.json',
      agentCardHandler({ agentCardProvider: requestHandler })
    );

    // Add auth middleware for API endpoints (skip for agent card)
    const authProvider = this.auth;
    const isNoAuth = authProvider instanceof NoAuth;
    if (!isNoAuth) {
      const authMiddleware: express.RequestHandler = async (req, res, next) => {
        const headers: Record<string, string> = {};
        for (const [key, value] of Object.entries(req.headers)) {
          if (typeof value === 'string') {
            headers[key] = value;
          }
        }
        const queryParams: Record<string, string> = {};
        for (const [key, value] of Object.entries(req.query)) {
          if (typeof value === 'string') {
            queryParams[key] = value;
          }
        }
        const result = await authProvider.authenticate({ headers, queryParams });
        if (!result.authenticated) {
          res.status(401).json({
            jsonrpc: '2.0',
            error: { code: -32600, message: result.error || 'Authentication failed' },
          });
          return;
        }
        next();
      };
      app.use('/a2a/jsonrpc', authMiddleware);
      app.use('/', authMiddleware);
    }

    app.use(
      '/a2a/jsonrpc',
      jsonRpcHandler({
        requestHandler,
        userBuilder: UserBuilder.noAuthentication,
      })
    );

    // Also support direct POST to root for backwards compatibility
    app.use(
      '/',
      jsonRpcHandler({
        requestHandler,
        userBuilder: UserBuilder.noAuthentication,
      })
    );

    // Add CORS headers if configured
    if (this.corsOrigins) {
      const origins = this.corsOrigins;
      app.use((req, res, next) => {
        const origin = req.headers.origin;
        if (origin && (origins.includes('*') || origins.includes(origin))) {
          res.setHeader('Access-Control-Allow-Origin', origin);
          res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
          res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-API-Key');
        }
        if (req.method === 'OPTIONS') {
          res.status(204).end();
          return;
        }
        next();
      });
    }

    return app;
  }

  /**
   * Start the A2A server.
   */
  async run(options: { host?: string; port?: number; logLevel?: string } = {}): Promise<void> {
    const { host = '0.0.0.0', port = 8787 } = options;

    // Run startup hooks
    for (const hook of this.onStartupHooks) {
      await hook();
    }

    // Production mode warning
    if (this.production) {
      const urlStr = this.url ?? `http://${host}:${port}`;
      if (!urlStr.startsWith('https://')) {
        console.warn(
          'WARNING: Running in production mode over HTTP. ' +
          'Consider using HTTPS for secure communication.'
        );
      }
    }

    const app = this.buildApp();
    const displayHost = host === '0.0.0.0' ? 'localhost' : host;

    const server = app.listen(port, host, () => {
      console.log(`
┌─────────────────────────────────────────────────┐
│  🚀 A2A Lite Agent Started                      │
├─────────────────────────────────────────────────┤
│  ${this.name} v${this.version}
│  ${this.description}
│
│  Skills:
${Array.from(this.skills.values())
  .map((s) => `│    • ${s.name}: ${s.description}${s.isStreaming ? ' [streaming]' : ''}`)
  .join('\n')}
│
│  Endpoints:
│    • Agent Card: http://${displayHost}:${port}/.well-known/agent.json
│    • JSON-RPC:   http://${displayHost}:${port}/a2a/jsonrpc
│    • API:        http://${displayHost}:${port}/
└─────────────────────────────────────────────────┘
      `);
    });

    // Handle shutdown
    const shutdown = async () => {
      console.log('\nShutting down...');
      for (const hook of this.onShutdownHooks) {
        await hook();
      }
      server.close();
      process.exit(0);
    };

    process.on('SIGINT', shutdown);
    process.on('SIGTERM', shutdown);
  }

  /**
   * Check if a function is a generator.
   */
  private isGeneratorFunction(fn: Function): boolean {
    return (
      fn.constructor.name === 'AsyncGeneratorFunction' ||
      fn.constructor.name === 'GeneratorFunction'
    );
  }

  /**
   * Detect if the handler expects a TaskContext parameter.
   * Analyzes the function's parameter names to identify common TaskContext parameter names.
   */
  private detectTaskContextParameter(handler: SkillHandler): { 
    needsTaskContext: boolean; 
    paramName?: string 
  } {
    // Get the function's source code to analyze parameter names
    const fnString = handler.toString();
    
    // Match destructured parameter patterns like: async ({ data, task }) => ...
    // or: async ({ data, ctx }) => ...
    const destructuredMatch = fnString.match(/\(\s*\{\s*[^}]*\b(task|ctx|context)\b[^}]*\}\s*\)/);
    
    if (destructuredMatch) {
      const paramName = destructuredMatch[1];
      return { needsTaskContext: true, paramName };
    }
    
    // Match regular parameter patterns like: async (data, task) => ...
    // But this is less common for TaskContext usage
    const regularMatch = fnString.match(/\(\s*(?:[^)]*,\s*)*\b(task|ctx|context)\b\s*\)/);
    
    if (regularMatch) {
      const paramName = regularMatch[1];
      return { needsTaskContext: true, paramName };
    }
    
    return { needsTaskContext: false };
  }
}
