/**
 * A2A Lite - Build A2A agents in 8 lines.
 *
 * Wraps the official @a2a-js/sdk with a simple, intuitive API.
 *
 * Simple:
 *   import { Agent } from 'a2a-lite';
 *
 *   const agent = new Agent({ name: "Bot", description: "My bot" });
 *
 *   agent.skill("greet", async ({ name }: { name: string }) => {
 *     return `Hello, ${name}!`;
 *   });
 *
 *   agent.run();
 *
 * Test it:
 *   import { AgentTestClient } from 'a2a-lite';
 *   const client = new AgentTestClient(agent);
 *   const result = await client.call("greet", { name: "World" });
 *
 * With streaming:
 *   agent.skill("chat", { streaming: true }, async function* ({ message }) {
 *     for (const word of message.split(' ')) {
 *       yield word + ' ';
 *     }
 *   });
 *
 * With auth:
 *   import { APIKeyAuth } from 'a2a-lite';
 *   const agent = new Agent({
 *     name: "SecureBot",
 *     auth: new APIKeyAuth({ keys: ["secret"] }),
 *   });
 */

// Core
export { Agent } from './agent.js';
export { LiteAgentExecutor } from './executor.js';

// Testing
export { AgentTestClient, TestClientError, TestResult } from './testing.js';

// Types
export type {
  AgentConfig,
  SkillConfig,
  SkillDefinition,
  SkillHandler,
  AuthProvider,
  AuthRequest,
  AuthResult,
  TaskState,
  TaskStatus,
  Task,
  TaskStore,
  LiteTextPart,
  LiteFilePart,
  LiteDataPart,
  LitePart,
  Artifact as IArtifact,
  Middleware,
  MiddlewareContext,
  MiddlewareNext,
} from './types.js';

// Re-export SDK types for advanced usage
export type { AgentCard, AgentSkill, Message, Part } from './types.js';

// Auth (optional)
export { NoAuth, APIKeyAuth, BearerAuth, CompositeAuth, OAuth2Auth } from './auth.js';

// Tasks (optional)
export { InMemoryTaskStore, TaskContext } from './tasks.js';

// MCP (optional)
export { MCPClient, MCPError, ToolNotFoundError } from './mcp/index.js';
export type { MCPToolResult, MCPToolDescriptor } from './mcp/index.js';

// Parts (optional)
export { FilePart, DataPart, Artifact, textPart, parsePart } from './parts.js';
