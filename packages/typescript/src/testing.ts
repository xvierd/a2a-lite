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

    // Create A2A JSON-RPC request
    const message = JSON.stringify({ skill, params });
    const requestBody = {
      jsonrpc: '2.0',
      method: 'message/send',
      id: Math.random().toString(36).slice(2),
      params: {
        message: {
          kind: 'message',
          role: 'user',
          messageId: Math.random().toString(36).slice(2),
          parts: [{ kind: 'text', text: message }],
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
        },
        hostname: 'localhost',
        get: (header: string) => {
          if (header.toLowerCase() === 'host') return 'localhost:8787';
          if (header.toLowerCase() === 'content-type') return 'application/json';
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
            resolve(data);
          }
        },
        end: () => {
          resolve(undefined);
        },
      };

      // Handle the request through Express
      app(mockReq as any, mockRes as any, (err?: any) => {
        if (err) reject(err instanceof Error ? err : new Error(String(err)));
      });
    });
  }

  /**
   * Call a streaming skill and collect all results.
   */
  async stream(skill: string, params: Record<string, unknown> = {}): Promise<unknown[]> {
    // Access skill directly for streaming tests
    const skills = (this.agent as any).skills as Map<string, any>;
    const skillDef = skills.get(skill);

    if (!skillDef) {
      throw new TestClientError(`Unknown skill: ${skill}`);
    }

    const results: unknown[] = [];
    const gen = skillDef.handler(params);

    if (gen[Symbol.asyncIterator]) {
      for await (const value of gen) {
        results.push(value);
      }
    } else if (gen[Symbol.iterator]) {
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
   * Extract result from A2A JSON-RPC response.
   */
  private extractResult(response: Record<string, unknown>): TestResult {
    if (response.error) {
      throw new TestClientError(JSON.stringify(response.error));
    }

    const result = response.result as Record<string, unknown>;

    // Handle A2A message format
    if (result?.parts) {
      const parts = result.parts as Array<{ kind?: string; type?: string; text?: string }>;
      const textPart = parts.find((p) => p.kind === 'text' || p.type === 'text');
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
