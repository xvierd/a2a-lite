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
  restHandler,
  UserBuilder,
} from '@a2a-js/sdk/server/express';
import type {
  AgentCard,
  AgentSkill,
  AgentCapabilities,
  AgentInterface,
  SecurityScheme,
  SecurityRequirement,
} from '@a2a-js/sdk';

import { LiteAgentExecutor } from './executor.js';
import type {
  AgentConfig,
  SkillConfig,
  SkillDefinition,
  SkillHandler,
  Middleware,
  TaskStore,
  AuthProvider,
} from './types.js';
import { type PushNotifier, TaskPushRegistry, createPushNotificationMiddleware } from './push-notifications.js';
import { InMemoryTaskStore as LiteTaskStore } from './tasks.js';
import { NoAuth } from './auth.js';
import type { AgentNetwork } from './orchestration.js';
import { callRemoteSkill, streamRemoteSkill, TaskHandle, discoverAgent } from './orchestration.js';

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
  private protocolTaskStore?: import('@a2a-js/sdk/server').TaskStore;
  private pushNotifier?: PushNotifier;
  readonly pushRegistry: TaskPushRegistry;
  private auth: AuthProvider;
  private network?: AgentNetwork;
  private hasStreaming = false;
  private corsOrigins?: string[];
  private production: boolean;
  private mcpServers: string[] = [];
  private mcpServerUrls: string[] = [];

  constructor(config: AgentConfig) {
    this.name = config.name;
    this.description = config.description;
    this.version = config.version ?? '1.0.0';
    this.url = config.url;
    this.corsOrigins = config.corsOrigins;
    this.production = config.production ?? false;
    this.mcpServers = config.mcpServers ?? [];

    // Setup task store
    if (config.taskStore === 'memory') {
      this.taskStore = new LiteTaskStore();
    } else if (config.taskStore) {
      this.taskStore = config.taskStore;
    }

    // Setup protocol task store
    this.protocolTaskStore = config.protocolTaskStore;

    // Setup push notifier
    this.pushNotifier = config.pushNotifier;

    // Always create a per-task push notification registry
    this.pushRegistry = new TaskPushRegistry();

    // Setup network
    this.network = config.network;

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
    const needsTaskContext = config.taskContext !== undefined
      ? !!config.taskContext
      : taskContextInfo.needsTaskContext;
    const taskContextParam = typeof config.taskContext === 'string'
      ? config.taskContext
      : taskContextInfo.paramName;

    // Auto-detect MCPClient parameter by analyzing the handler
    const mcpInfo = this.detectMCPClientParameter(handler);
    const needsMcp = config.mcp !== undefined
      ? !!config.mcp
      : mcpInfo.needsMcp;
    const mcpParam = typeof config.mcp === 'string'
      ? config.mcp
      : mcpInfo.paramName;

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
      needsMcp,
      mcpParam,
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
   * Register an MCP server for tool access in skills.
   *
   * Skills can access MCP tools via the MCPClient passed in context.
   *
   * Requires: npm install @modelcontextprotocol/sdk
   *
   * @param url - The MCP server URL (e.g., "http://localhost:5001/sse")
   */
  addMcpServer(url: string): this {
    this.mcpServerUrls.push(url);
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
   * Delegate a skill call to a remote agent.
   *
   * The target can be a full URL or a name registered in this agent's network.
   *
   *   const result = await agent.delegate("http://weather:8787", "forecast", { city: "NYC" });
   *
   *   // Or with a network:
   *   const result = await agent.delegate("weather", "forecast", { city: "NYC" });
   *
   *   // With discovery and task handle:
   *   const handle = await agent.delegate("weather", "forecast", { city: "NYC" }, {
   *     discover: true,
   *     returnHandle: true,
   *   });
   *
   *   // With streaming:
   *   for await (const chunk of await agent.delegate("story", "tellStory", { topic }, { stream: true })) {
   *     process.stdout.write(chunk);
   *   }
   */
  async delegate(
    target: string,
    skill: string,
    params?: Record<string, unknown>,
    options?: { timeout?: number; returnHandle?: boolean; discover?: boolean; stream: true },
  ): Promise<AsyncGenerator<string>>;
  async delegate(
    target: string,
    skill: string,
    params?: Record<string, unknown>,
    options?: { timeout?: number; returnHandle?: boolean; discover?: boolean; stream?: false },
  ): Promise<unknown>;
  /** @deprecated Use the options-object overload instead. */
  async delegate(
    target: string,
    skill: string,
    params?: Record<string, unknown>,
    timeout?: number,
  ): Promise<unknown>;
  async delegate(
    target: string,
    skill: string,
    params: Record<string, unknown> = {},
    timeoutOrOptions?: number | { timeout?: number; returnHandle?: boolean; discover?: boolean; stream?: boolean },
  ): Promise<unknown | AsyncGenerator<string>> {
    let timeout = 30000;
    let returnHandle = false;
    let discover = false;
    let stream = false;

    if (typeof timeoutOrOptions === 'number') {
      timeout = timeoutOrOptions;
    } else if (timeoutOrOptions) {
      timeout = timeoutOrOptions.timeout ?? 30000;
      returnHandle = timeoutOrOptions.returnHandle ?? false;
      discover = timeoutOrOptions.discover ?? false;
      stream = timeoutOrOptions.stream ?? false;
    }

    let url = target;
    if (this.network && !target.startsWith('http://') && !target.startsWith('https://')) {
      const resolved = this.network.get(target);
      if (resolved === undefined) {
        throw new Error(
          `Agent '${target}' not found in network. Available: ${Object.keys(this.network.list()).join(', ')}`
        );
      }
      url = resolved;
    }

    // Optionally discover the agent card and validate the skill exists
    if (discover) {
      const card = await discoverAgent(url, timeout);
      const skillExists = card.skills.some((s) => s.id === skill || s.name === skill);
      if (!skillExists) {
        const available = card.skills.map((s) => s.id).join(', ');
        throw new Error(
          `Skill '${skill}' not found on agent '${card.name}' at ${url}. Available: ${available}`,
        );
      }
      // Use the card's advertised URL if present
      if (card.url) {
        url = card.url;
      }
    }

    // Streaming mode — return an async generator
    if (stream) {
      return streamRemoteSkill(url, skill, params, timeout);
    }

    if (returnHandle) {
      // Use the network's call with returnHandle if available, otherwise do it inline
      if (this.network && !target.startsWith('http://') && !target.startsWith('https://')) {
        return this.network.call(target, skill, params, timeout, { returnHandle: true });
      }
      // For direct URLs, import the internal helper indirectly via callRemoteSkill pattern
      const { callRemoteSkillWithHandle } = await import('./orchestration.js');
      return callRemoteSkillWithHandle(url, skill, params, timeout);
    }

    return callRemoteSkill(url, skill, params, timeout);
  }

  /**
   * Build the A2A v1.0-compliant Agent Card.
   */
  buildAgentCard(host = 'localhost', port = 8787): AgentCard {
    const skills: AgentSkill[] = Array.from(this.skills.values()).map((s) => ({
      id: s.name,
      name: s.name,
      description: s.description,
      tags: s.tags,
      examples: [],
      inputModes: ['application/json'],
      outputModes: ['application/json'],
      securityRequirements: [],
    }));

    const url = this.url ?? `http://${host}:${port}`;

    const supportedInterfaces: AgentInterface[] = [
      { url, protocolBinding: 'JSONRPC', protocolVersion: '1.0', tenant: '' },
      { url, protocolBinding: 'HTTP+JSON', protocolVersion: '1.0', tenant: '' },
    ];

    const capabilities: AgentCapabilities = {
      streaming: this.hasStreaming,
      pushNotifications: true,
      extensions: [],
    };

    const { securitySchemes, securityRequirements } = this.buildSecuritySchemes();

    return {
      name: this.name,
      description: this.description,
      supportedInterfaces,
      provider: undefined,
      version: this.version,
      capabilities,
      securitySchemes,
      securityRequirements,
      defaultInputModes: ['application/json'],
      defaultOutputModes: ['application/json'],
      skills,
      signatures: [],
    };
  }

  /**
   * Convert the auth provider's scheme to A2A v1.0 security scheme types.
   * Returns empty map/list when no auth provider (or NoAuth) is configured.
   */
  private buildSecuritySchemes(): {
    securitySchemes: { [key: string]: SecurityScheme };
    securityRequirements: SecurityRequirement[];
  } {
    const empty = { securitySchemes: {}, securityRequirements: [] };
    if (!this.auth || this.auth instanceof NoAuth) {
      return empty;
    }

    const scheme = this.auth.getScheme();
    if (!scheme || Object.keys(scheme).length === 0) {
      return empty;
    }

    const schemeType = scheme.type as string | undefined;
    let name: string;
    let securityScheme: SecurityScheme;

    if (schemeType === 'apiKey') {
      name = 'apiKey';
      securityScheme = {
        scheme: {
          $case: 'apiKeySecurityScheme',
          value: {
            description: '',
            name: (scheme.name as string) ?? 'X-API-Key',
            location: (scheme.in as string) ?? 'header',
          },
        },
      };
    } else if (schemeType === 'http') {
      name = (scheme.scheme as string) ?? 'http';
      securityScheme = {
        scheme: {
          $case: 'httpAuthSecurityScheme',
          value: {
            description: '',
            scheme: (scheme.scheme as string) ?? 'bearer',
            bearerFormat: 'JWT',
          },
        },
      };
    } else if (schemeType === 'oauth2') {
      name = 'oauth2';
      const flows = (scheme.flows ?? {}) as Record<string, Record<string, unknown>>;
      const authCode = flows.authorizationCode ?? {};
      securityScheme = {
        scheme: {
          $case: 'oauth2SecurityScheme',
          value: {
            description: '',
            flows: {
              flow: {
                $case: 'authorizationCode',
                value: {
                  authorizationUrl: (authCode.authorizationUrl as string) ?? '',
                  tokenUrl: (authCode.tokenUrl as string) ?? '',
                  refreshUrl: '',
                  scopes: (authCode.scopes as Record<string, string>) ?? {},
                  pkceRequired: false,
                },
              },
            },
            oauth2MetadataUrl: '',
          },
        },
      };
    } else {
      console.warn(`[A2A] Unknown auth scheme type '${schemeType}'; skipping agent card security schemes`);
      return empty;
    }

    return {
      securitySchemes: { [name]: securityScheme },
      securityRequirements: [{ schemes: { [name]: { list: [] } } }],
    };
  }

  /**
   * Build the Express app using the official SDK handlers.
   *
   * @param host - Host used for the agent card's advertised URL (default: 'localhost')
   * @param port - Port used for the agent card's advertised URL (default: 8787)
   */
  buildApp(host = 'localhost', port = 8787): Express {
    const app = express();

    // Auto-register push notifier as an onComplete hook
    if (this.pushNotifier) {
      const notifier = this.pushNotifier;
      const agentName = this.name;
      this.onCompleteHooks.unshift(async (skill: string, result: unknown) => {
        try {
          await notifier.notify({
            skill,
            result,
            status: 'completed',
            timestamp: Date.now() / 1000,
            agent: agentName,
          });
        } catch (err) {
          console.warn('[A2A] Push notifier error:', err);
        }
      });
    }

    // Create the executor that bridges to our skills
    const executor = new LiteAgentExecutor({
      skills: this.skills,
      errorHandler: this.errorHandler,
      middlewares: this.middlewares,
      onCompleteHooks: this.onCompleteHooks,
      authProvider: this.auth,
      taskStore: this.taskStore,
      mcpServers: this.mcpServers,
      pushRegistry: this.pushRegistry,
    });

    // Create the SDK's request handler
    const agentCard = this.buildAgentCard(host, port);
    const requestHandler = new DefaultRequestHandler(
      agentCard,
      this.protocolTaskStore ?? new InMemoryTaskStore(),
      executor
    );

    // Mount SDK handlers — agent card at the A2A v1.0 well-known path
    app.use(
      '/.well-known/agent-card.json',
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
      app.use('/', authMiddleware);
    }

    // Per-task push notification middleware (must come before SDK JSON-RPC handler)
    app.use('/', express.json(), createPushNotificationMiddleware(this.pushRegistry));

    // JSON-RPC transport at the base URL (A2A v1.0 methods: SendMessage, ...)
    app.use(
      '/',
      jsonRpcHandler({
        requestHandler,
        userBuilder: UserBuilder.noAuthentication,
      })
    );

    // HTTP+JSON (REST) transport — out of the box in SDK 1.x
    app.use(
      '/',
      restHandler({
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

    const displayHost = host === '0.0.0.0' ? 'localhost' : host;
    const app = this.buildApp(displayHost, port);

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
│    • Agent Card: http://${displayHost}:${port}/.well-known/agent-card.json
│    • JSON-RPC:   http://${displayHost}:${port}/
│    • REST:       http://${displayHost}:${port}/message:send
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
   * Return skills as OpenAI-compatible tool schemas for use with LLM APIs.
   *
   * Usage with OpenAI:
   *   const tools = agent.getToolSchemas();
   *   const response = await openai.chat.completions.create({ model: "gpt-4o", messages, tools });
   *
   * Usage with Anthropic (same format works):
   *   const tools = agent.getToolSchemas();
   *   const response = await anthropic.messages.create({ model: "...", messages, tools });
   */
  getToolSchemas(format: 'openai' = 'openai'): Array<Record<string, unknown>> {
    if (format !== 'openai') {
      throw new Error(`Unsupported schema format: '${format}'. Use 'openai'.`);
    }

    return Array.from(this.skills.values()).map((skill) => ({
      type: 'function',
      function: {
        name: skill.name,
        description: skill.description,
        parameters: Object.keys(skill.inputSchema).length > 0
          ? skill.inputSchema
          : { type: 'object', properties: {} },
      },
    }));
  }

  /**
   * Check if a function is a generator.
   */
  private isGeneratorFunction(fn: SkillHandler): boolean {
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

  /**
   * Detect if the handler expects an MCPClient parameter.
   * Analyzes the function's parameter names to identify common MCP parameter names.
   */
  private detectMCPClientParameter(handler: SkillHandler): {
    needsMcp: boolean;
    paramName?: string
  } {
    // Get the function's source code to analyze parameter names
    const fnString = handler.toString();

    // Match destructured parameter patterns like: async ({ query, mcp }) => ...
    const destructuredMatch = fnString.match(/\(\s*\{\s*[^}]*\b(mcp|mcpClient)\b[^}]*\}\s*\)/);

    if (destructuredMatch) {
      const paramName = destructuredMatch[1];
      return { needsMcp: true, paramName };
    }

    return { needsMcp: false };
  }
}
