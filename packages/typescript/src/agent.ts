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

import express, { Express, type ErrorRequestHandler } from 'express';
import { DefaultRequestHandler, InMemoryTaskStore, ServerCallContext } from '@a2a-js/sdk/server';
import { agentCardHandler, jsonRpcHandler, restHandler } from '@a2a-js/sdk/server/express';
import { AgentCard } from '@a2a-js/sdk';
import type { AgentSkill, AgentCapabilities, AgentInterface, SecurityScheme, SecurityRequirement } from '@a2a-js/sdk';

import { boundedTaskStore } from './bounded-task-store.js';
import { RuntimeControl, startRuntime, type AgentRuntime } from './runtime.js';
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
import { type PushNotifier, TaskPushRegistry } from './push-notifications.js';
import { InMemoryTaskStore as LiteTaskStore } from './tasks.js';
import { NoAuth } from './auth.js';
import { createHttpAuthentication } from './http-auth.js';
import { authorizedHandler } from './authorization.js';
import { ProtocolPushStore, ProtocolPushSender } from './protocol-push.js';
import type { AgentNetwork } from './orchestration.js';
import { bindRemoteOptions, type RemoteCallOptions } from './remote-auth.js';
import { callRemoteSkill, streamRemoteSkill, discoverAgent } from './orchestration.js';

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
  /** @deprecated Standalone legacy registry; protocol callbacks use the scoped SDK store. */
  readonly pushRegistry: TaskPushRegistry;
  private auth: AuthProvider;
  private network?: AgentNetwork;
  private hasStreaming = false;
  private corsOrigins?: string[];
  private production: boolean;
  private mcpServers: string[] = [];
  private mcpServerUrls: string[] = [];
  private config: AgentConfig;
  private running?: AgentRuntime;
  private starting = false;

  constructor(config: AgentConfig) {
    this.config = config;
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
  skill(name: string, configOrHandler: SkillConfig | SkillHandler, maybeHandler?: SkillHandler): this {
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
    const needsTaskContext = config.taskContext !== undefined ? !!config.taskContext : taskContextInfo.needsTaskContext;
    const taskContextParam = typeof config.taskContext === 'string' ? config.taskContext : taskContextInfo.paramName;

    // Auto-detect MCPClient parameter by analyzing the handler
    const mcpInfo = this.detectMCPClientParameter(handler);
    const needsMcp = config.mcp !== undefined ? !!config.mcp : mcpInfo.needsMcp;
    const mcpParam = typeof config.mcp === 'string' ? config.mcp : mcpInfo.paramName;

    const needsInteraction = config.interaction ?? false;

    const skillDef: SkillDefinition = {
      name: skillName,
      description: config.description ?? `Skill: ${skillName}`,
      tags: config.tags ?? [],
      handler,
      inputSchema: {},
      outputSchema: {},
      isStreaming,
      taskMode: config.task ?? needsTaskContext,
      checkpoint: config.checkpoint,
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
    options?: RemoteCallOptions & { timeout?: number; returnHandle?: boolean; discover?: boolean; stream: true },
  ): Promise<AsyncGenerator<string>>;
  async delegate(
    target: string,
    skill: string,
    params?: Record<string, unknown>,
    options?: RemoteCallOptions & { timeout?: number; returnHandle?: boolean; discover?: boolean; stream?: false },
  ): Promise<unknown>;
  /** @deprecated Use the options-object overload instead. */
  async delegate(target: string, skill: string, params?: Record<string, unknown>, timeout?: number): Promise<unknown>;
  async delegate(
    target: string,
    skill: string,
    params: Record<string, unknown> = {},
    timeoutOrOptions?:
      | number
      | (RemoteCallOptions & { timeout?: number; returnHandle?: boolean; discover?: boolean; stream?: boolean }),
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
          `Agent '${target}' not found in network. Available: ${Object.keys(this.network.list()).join(', ')}`,
        );
      }
      url = resolved;
    }

    const credentials = bindRemoteOptions(
      { ...this.network?.getCredentials(target), ...(typeof timeoutOrOptions === 'object' ? timeoutOrOptions : {}) },
      url,
    );

    // Optionally discover the agent card and validate the skill exists
    if (discover) {
      const card = await discoverAgent(url, timeout, credentials);
      const skillExists = card.skills.some((s) => s.id === skill || s.name === skill);
      if (!skillExists) {
        const available = card.skills.map((s) => s.id).join(', ');
        throw new Error(`Skill '${skill}' not found on agent '${card.name}' at ${url}. Available: ${available}`);
      }
      // Use the card's advertised URL if present
      if (card.url) {
        url = card.url;
      }
    }

    // Streaming mode — return an async generator
    if (stream) {
      return streamRemoteSkill(url, skill, params, timeout, credentials);
    }

    if (returnHandle) {
      // For direct URLs, import the internal helper indirectly via callRemoteSkill pattern
      const { callRemoteSkillWithHandle } = await import('./orchestration.js');
      return callRemoteSkillWithHandle(url, skill, params, timeout, credentials);
    }

    return callRemoteSkill(url, skill, params, timeout, credentials);
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
    const profile = this.config.profile ?? 'learning';
    if (profile !== 'learning' && (this.auth instanceof NoAuth || this.auth.getScheme().anonymous === true))
      throw new Error('Authenticated profiles require an authentication provider without anonymous fallback.');
    if (profile === 'durable' && !this.config.persistence?.durable)
      throw new Error('Durable profile requires configured persistent protocol stores.');
    const control = new RuntimeControl(this.config.limits, this.config.telemetry);
    app.locals.a2aControl = control;
    app.get('/health/live', (_req, res) => res.json({ status: 'live' }));
    app.get('/health/ready', async (_req, res) => {
      const ready = !control.stats.closing && (!this.config.persistence || (await this.config.persistence.ready()));
      res.status(ready ? 200 : 503).json({ ready });
    });

    // CORS must run before auth and SDK handlers, including for preflight requests.
    if (this.corsOrigins) {
      const origins = this.corsOrigins;
      app.use((req, res, next) => {
        const origin = req.headers.origin;
        res.vary('Origin');
        if (origin && (origins.includes('*') || origins.includes(origin))) {
          res.setHeader('Access-Control-Allow-Origin', origin);
          res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
          res.setHeader(
            'Access-Control-Allow-Headers',
            'Content-Type, Authorization, X-API-Key, A2A-Version, A2A-Extensions',
          );
          res.setHeader('Access-Control-Expose-Headers', 'A2A-Version, A2A-Extensions');
        }
        if (req.method === 'OPTIONS') {
          res.status(204).end();
          return;
        }
        next();
      });
    }

    // Keep app construction from adding duplicate notifier hooks to the agent.
    const onCompleteHooks = [...this.onCompleteHooks];
    if (this.pushNotifier) {
      const notifier = this.pushNotifier;
      const agentName = this.name;
      onCompleteHooks.unshift(async (skill: string, result: unknown) => {
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

    const protocolTaskStore = boundedTaskStore(
      this.config.persistence?.taskStore ?? this.protocolTaskStore ?? new InMemoryTaskStore(),
      {
        maxHistory: control.limits.maxTaskHistory,
        maxBytes: control.limits.maxTaskBytes,
        maxTasks: !this.config.persistence && !this.protocolTaskStore ? control.limits.maxStoredTasks : undefined,
      },
    );

    // Create the executor that bridges to our skills
    const executor = new LiteAgentExecutor({
      skills: this.skills,
      errorHandler: this.errorHandler,
      middlewares: this.middlewares,
      onCompleteHooks,
      authProvider: this.auth,
      taskStore: this.taskStore,
      mcpServers: this.mcpServers,
      executionTimeoutMs: control.limits.executionTimeoutMs,
      maxExecutions: control.limits.maxConcurrentRequests,
      maxTaskHistory: control.limits.maxTaskHistory,
      executionCoordinator: this.config.persistence?.execution,
      maxEventsPerExecution: control.limits.maxEventsPerExecution,
      maxOutputBytes: control.limits.maxOutputBytes,
      waitForTerminal: async (id, request) => {
        const context = new ServerCallContext({ user: request.context.user, tenant: request.context.tenant });
        const until = Date.now() + control.limits.shutdownGraceMs;
        while (Date.now() < until) {
          const task = await protocolTaskStore.load(id, context);
          if (task?.status && [3, 4, 5, 7].includes(task.status.state)) return;
          await new Promise((resolve) => setTimeout(resolve, 10));
        }
        throw new Error('Task shutdown settlement deadline exceeded');
      },
    });

    app.locals.a2aClose = async () => {
      try {
        await executor.close();
      } finally {
        await this.config.persistence?.close();
      }
    };

    // Create the SDK's request handler
    const agentCard = this.buildAgentCard(host, port);
    app.locals.a2aCard = agentCard;
    const pushStore = new ProtocolPushStore(
      this.config.persistence?.pushStore ?? this.config.protocolPushStore,
      control.limits.maxPushConfigsPerTask,
    );
    const requestHandler = authorizedHandler(
      new DefaultRequestHandler(
        agentCard,
        protocolTaskStore,
        executor,
        this.config.persistence?.execution?.eventBusManager,
        pushStore,
        this.config.persistence?.pushSender ?? new ProtocolPushSender(pushStore),
      ),
      this.config.persistence?.execution,
    );

    // Mount SDK handlers — agent card at the A2A v1.0 well-known path
    app.use(
      '/.well-known/agent-card.json',
      agentCardHandler({
        // SDK1.3's Express card handler JSON.stringify's its provider directly.
        // Its protobuf oneofs therefore need the SDK wire serializer here.
        agentCardProvider: async () =>
          Object.assign({}, await requestHandler.getAgentCard(), { toJSON: () => AgentCard.toJSON(agentCard) }),
      }),
    );

    const authentication = createHttpAuthentication(this.auth, profile !== 'learning');
    app.use('/', authentication.middleware);
    app.use(express.json({ limit: control.limits.bodyLimitBytes, type: ['application/json', 'application/a2a+json'] }));
    app.use((req, res, next) => {
      // AgentTestClient's direct Express invocation has no socket lifecycle.
      if (typeof res.once === 'function') control.middleware(req, res, next);
      else next();
    });

    // Scope JSON-RPC's content-type guard to its endpoint so REST can accept application/a2a+json.
    app.post(
      '/',
      jsonRpcHandler({
        requestHandler,
        userBuilder: authentication.userBuilder,
        contextBuilder: authentication.contextBuilder,
      }),
    );

    // HTTP+JSON (REST) transport — out of the box in SDK 1.x
    app.use(
      '/',
      restHandler({
        requestHandler,
        userBuilder: authentication.userBuilder,
        contextBuilder: authentication.contextBuilder,
      }),
    );

    app.use(((error, _req, res, _next) => {
      const status = (error as { type?: string }).type === 'entity.too.large' ? 413 : 400;
      if (!res.headersSent)
        res.status(status).json({ error: status === 413 ? 'Request body too large' : 'Invalid request body' });
    }) as ErrorRequestHandler);
    return app;
  }

  /**
   * Start the A2A server.
   */
  async start(options: { host?: string; port?: number; logLevel?: string } = {}): Promise<AgentRuntime> {
    if (this.starting || this.running) throw new Error('Agent already started');
    this.starting = true;
    const { host = '0.0.0.0', port = 8787 } = options;
    let app: Express | undefined;
    let closed = false;
    const closeResources = async () => {
      if (closed) return;
      closed = true;
      const results = await Promise.allSettled([
        app?.locals.a2aClose?.(),
        ...this.onShutdownHooks.map(async (hook) => hook()),
      ]);
      this.running = undefined;
      const failure = results.find((result) => result.status === 'rejected');
      if (failure?.status === 'rejected') throw failure.reason;
    };
    try {
      app = this.buildApp(host, port);
      if (this.config.persistence && !(await this.config.persistence.ready()))
        throw new Error('Protocol storage is not ready; apply SDK migrations before startup.');
      for (const hook of this.onStartupHooks) await hook();
      const runtime = await startRuntime(app, host, port, app.locals.a2aControl as RuntimeControl, closeResources);
      if (port === 0 && !this.url)
        for (const endpoint of (app.locals.a2aCard as AgentCard).supportedInterfaces) endpoint.url = runtime.url;
      this.config.persistence?.start?.();
      this.running = runtime;
      return runtime;
    } catch (error) {
      await closeResources();
      throw error;
    } finally {
      this.starting = false;
    }
  }

  /** Start a managed runtime. CLI callers may install their own signal handlers. */
  async run(options: { host?: string; port?: number; logLevel?: string } = {}): Promise<AgentRuntime> {
    const runtime = await this.start(options);
    console.log(`A2A Lite ${this.name} listening at ${runtime.url}`);
    return runtime;
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
        parameters: Object.keys(skill.inputSchema).length > 0 ? skill.inputSchema : { type: 'object', properties: {} },
      },
    }));
  }

  /**
   * Check if a function is a generator.
   */
  private isGeneratorFunction(fn: SkillHandler): boolean {
    return fn.constructor.name === 'AsyncGeneratorFunction' || fn.constructor.name === 'GeneratorFunction';
  }

  /**
   * Detect if the handler expects a TaskContext parameter.
   * Analyzes the function's parameter names to identify common TaskContext parameter names.
   */
  private detectTaskContextParameter(handler: SkillHandler): {
    needsTaskContext: boolean;
    paramName?: string;
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
    paramName?: string;
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
