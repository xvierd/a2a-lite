/**
 * Core types for A2A Lite TypeScript.
 *
 * These types extend and simplify the official @a2a-js/sdk types.
 */

// Re-export SDK types that we use directly
export type {
  AgentCard,
  AgentSkill,
  Message,
  Part,
  TextPart,
  FilePart as A2AFilePart,
  DataPart as A2ADataPart,
} from '@a2a-js/sdk';

export interface AgentConfig {
  name: string;
  description: string;
  version?: string;
  url?: string;
  auth?: AuthProvider;
  taskStore?: TaskStore | 'memory';
  /**
   * Explicit task store passed directly to the A2A protocol layer.
   * When provided, this store is used by the SDK's DefaultRequestHandler
   * instead of its internal InMemoryTaskStore.  Useful for persistence
   * across restarts (e.g. a Redis-backed store).
   */
  protocolTaskStore?: import('@a2a-js/sdk/server').TaskStore;
  /**
   * Push notifier called after every skill completion.
   * Use `LogPushNotifier` in development or `WebhookPushNotifier` for production.
   */
  pushNotifier?: import('./push-notifications.js').PushNotifier;
  network?: import('./orchestration.js').AgentNetwork;
  corsOrigins?: string[];
  production?: boolean;
  mcpServers?: string[];  // MCP server URLs
  /**
   * SDK-level task store for A2A protocol task lifecycle persistence.
   * Enables Redis, PostgreSQL, or any custom persistent storage.
   * Different from taskStore which is for skill-level TaskContext tracking.
   *
   * Must implement the SDK's TaskStore interface from @a2a-js/sdk.
   *
   * @example
   * import { RedisTaskStore } from './my-stores';
   * const agent = new Agent({ protocolTaskStore: new RedisTaskStore() });
   */
  protocolTaskStore?: unknown; // accepts any SDK-compatible TaskStore
  /**
   * Push notifier for skill completion events.
   * Called after every successful or failed skill execution.
   *
   * @example
   * import { WebhookPushNotifier } from './push-notifications';
   * const agent = new Agent({
   *   pushNotifier: new WebhookPushNotifier({ url: 'https://...' })
   * });
   */
  pushNotifier?: import('./push-notifications.js').PushNotifier;
}

export interface SkillConfig {
  name?: string;
  description?: string;
  tags?: string[];
  streaming?: boolean;
  taskContext?: boolean | string;  // true or param name
  interaction?: boolean;
  mcp?: boolean | string;          // true or param name
}

export interface SkillDefinition {
  name: string;
  description: string;
  tags: string[];
  handler: SkillHandler;
  inputSchema: Record<string, unknown>;
  outputSchema: Record<string, unknown>;
  isStreaming: boolean;
  needsTaskContext: boolean;
  needsInteraction: boolean;
  taskContextParam?: string;  // Name of the parameter that receives TaskContext
  needsMcp: boolean;          // Whether skill needs MCPClient injection
  mcpParam?: string;          // Name of the parameter that receives MCPClient
}

export type SkillHandler = (
  params: Record<string, unknown>
) => Promise<unknown> | AsyncGenerator<unknown>;

// Auth types
export interface AuthRequest {
  headers: Record<string, string>;
  queryParams?: Record<string, string>;
}

export interface AuthResult {
  authenticated: boolean;
  userId?: string;
  scopes?: Set<string>;
  error?: string;
}

export interface AuthProvider {
  authenticate(request: AuthRequest): Promise<AuthResult>;
  getScheme(): Record<string, unknown>;
}

// Task types
export type TaskState =
  | 'submitted'
  | 'working'
  | 'input-required'
  | 'completed'
  | 'failed'
  | 'canceled';

export interface TaskStatus {
  state: TaskState;
  message?: string;
  progress?: number;
  timestamp: Date;
}

export interface Task {
  id: string;
  skill: string;
  params: Record<string, unknown>;
  status: TaskStatus;
  history: TaskStatus[];
  createdAt: Date;
  updatedAt: Date;
}

export interface TaskStore {
  create(skill: string, params: Record<string, unknown>): Task;
  get(id: string): Task | undefined;
  update(task: Task): void;
  delete(id: string): boolean;
  list(options?: { skill?: string; state?: TaskState }): Task[];
}

// Simplified Part types for a2a-lite
export interface LiteFilePart {
  type: 'file';
  name: string;
  mimeType: string;
  data?: Buffer;
  uri?: string;
}

export interface LiteDataPart {
  type: 'data';
  data: Record<string, unknown>;
}

export interface LiteTextPart {
  type: 'text';
  text: string;
}

export type LitePart = LiteTextPart | LiteFilePart | LiteDataPart;

export interface Artifact {
  name?: string;
  description?: string;
  parts: LitePart[];
  metadata?: Record<string, unknown>;
}

// Middleware types
export interface MiddlewareContext {
  skill: string;
  params: Record<string, unknown>;
  message: string;
  metadata: Record<string, unknown>;
}

export type MiddlewareNext = () => Promise<unknown>;
export type Middleware = (ctx: MiddlewareContext, next: MiddlewareNext) => Promise<unknown>;
