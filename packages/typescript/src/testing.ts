/**
 * Testing utilities for A2A Lite TypeScript.
 *
 * Makes testing agents as simple as:
 *
 *   import { AgentTestClient } from 'a2a-lite';
 *
 *   const client = new AgentTestClient(agent);
 *   const result = await client.call("greet", { name: "World" });
 *   expect(result).toBe("Hello, World!");
 */

import type { Agent } from './agent.js';
import type { AgentCard } from '@a2a-js/sdk';
import type { Request, Response, NextFunction } from 'express';
import type { SkillDefinition } from './types.js';

/**
 * Internal interface used to access private Agent fields in tests
 * without resorting to `as any`.
 */
interface AgentInternals {
  skills: Map<string, SkillDefinition>;
}

/** Type guard: checks if a value is async iterable. */
function isAsyncIterable(value: unknown): value is AsyncIterable<unknown> {
  return value !== null && typeof value === 'object' && Symbol.asyncIterator in (value as object);
}

/** Type guard: checks if a value is (sync) iterable. */
function isIterable(value: unknown): value is Iterable<unknown> {
  return value !== null && typeof value === 'object' && Symbol.iterator in (value as object);
}

/**
 * Structured result from a test client call.
 *
 * Provides multiple ways to access the result:
 * - .data — parsed JavaScript value (object, array, number, string, etc.)
 * - .text — raw text string
 * - .json() — parse text as JSON (throws on invalid JSON)
 */
export class TestResult {
  private _data: unknown;
  private _text: string;

  constructor(data: unknown, text: string) {
    this._data = data;
    this._text = text;
  }

  get data(): unknown {
    return this._data;
  }

  get text(): string {
    return this._text;
  }

  json(): unknown {
    return JSON.parse(this._text);
  }

  toString(): string {
    return `TestResult(${JSON.stringify(this._data)})`;
  }
}

export class AgentTestClient {
  private agent: Agent;
  private baseUrl: string;

  constructor(agent: Agent, options?: { baseUrl?: string }) {
    this.agent = agent;
    this.baseUrl = options?.baseUrl ?? 'http://localhost:8787';
  }

  /**
   * Call a skill and return the result.
   */
  async call(skill: string, params: Record<string, unknown> = {}): Promise<TestResult> {
    const app = this.agent.buildApp();

    // Create A2A v1.0 JSON-RPC request
    const message = JSON.stringify({ skill, params });
    const requestBody = {
      jsonrpc: '2.0',
      method: 'SendMessage',
      id: Math.random().toString(36).slice(2),
      params: {
        message: {
          role: 'ROLE_USER',
          messageId: Math.random().toString(36).slice(2),
          parts: [{ text: message }],
        },
      },
    };

    // Use a promise-based approach to invoke the route handler
    return new Promise((resolve, reject) => {
      const mockReq = {
        body: requestBody,
        method: 'POST',
        url: '/',
        headers: {
          'content-type': 'application/json',
          'a2a-version': '1.0',
        },
        hostname: 'localhost',
        get: (header: string) => {
          if (header.toLowerCase() === 'host') return 'localhost:8787';
          if (header.toLowerCase() === 'content-type') return 'application/json';
          if (header.toLowerCase() === 'a2a-version') return '1.0';
          return undefined;
        },
      };

      const mockRes = {
        statusCode: 200,
        headers: {} as Record<string, string>,
        setHeader: (name: string, value: string) => {
          mockRes.headers[name.toLowerCase()] = value;
        },
        getHeader: (name: string) => mockRes.headers[name.toLowerCase()],
        status: (code: number) => {
          mockRes.statusCode = code;
          return mockRes;
        },
        json: (data: Record<string, unknown>) => {
          try {
            const result = this.extractResult(data);
            resolve(result);
          } catch (err) {
            reject(err);
          }
        },
        send: (data: string) => {
          try {
            const parsed = JSON.parse(data);
            const result = this.extractResult(parsed);
            resolve(result);
          } catch {
            console.debug('Response is not JSON, returning raw text');
            resolve(new TestResult(data, data));
          }
        },
        end: () => {
          resolve(new TestResult(undefined, ''));
        },
      };

      // Handle the request through Express
      const next: NextFunction = (err?: unknown) => {
        if (err) reject(err instanceof Error ? err : new Error(String(err)));
      };
      app(mockReq as unknown as Request, mockRes as unknown as Response, next);
    });
  }

  /**
   * Call a streaming skill and collect all results.
   */
  async stream(skill: string, params: Record<string, unknown> = {}): Promise<unknown[]> {
    // Access skill directly for streaming tests via typed internal interface
    const skills = (this.agent as unknown as AgentInternals).skills;
    const skillDef = skills.get(skill);

    if (!skillDef) {
      throw new TestClientError(`Unknown skill: ${skill}`);
    }

    const results: unknown[] = [];
    const gen = skillDef.handler(params);

    if (isAsyncIterable(gen)) {
      for await (const value of gen) {
        results.push(value);
      }
    } else if (isIterable(gen)) {
      for (const value of gen) {
        results.push(value);
      }
    } else {
      results.push(await gen);
    }

    return results;
  }

  /**
   * Get the agent card.
   */
  getAgentCard(): AgentCard {
    return this.agent.buildAgentCard();
  }

  /**
   * List available skills.
   */
  listSkills(): string[] {
    const card = this.getAgentCard();
    return card.skills?.map((s) => s.name) ?? [];
  }

  /**
   * Extract result from A2A v1.0 JSON-RPC response.
   * The result envelope is `{ message: {...} }` or `{ task: {...} }`;
   * text parts use the `{ "text": ... }` wire shape.
   */
  private extractResult(response: Record<string, unknown>): TestResult {
    if (response.error) {
      throw new TestClientError(JSON.stringify(response.error));
    }

    const envelope = (response.result ?? {}) as Record<string, unknown>;
    const result = (envelope.message ?? envelope.task ?? envelope) as Record<string, unknown>;

    // Handle A2A message format
    if (result?.parts) {
      const parts = result.parts as Array<{ text?: string }>;
      const textPart = parts.find((p) => typeof p.text === 'string');
      if (textPart?.text) {
        let data: unknown;
        try {
          data = JSON.parse(textPart.text);
        } catch {
          console.debug('Result text is not JSON, returning as string');
          data = textPart.text;
        }
        return new TestResult(data, textPart.text);
      }
    }

    const text = JSON.stringify(result);
    return new TestResult(result, text);
  }
}

export class TestClientError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'TestClientError';
  }
}

/**
 * Async-explicit test client — same as AgentTestClient.
 *
 * Provided for API parity with the Python SDK's AsyncAgentTestClient.
 * In TypeScript everything is already async, so this is an alias.
 */
export class AsyncAgentTestClient extends AgentTestClient {}
