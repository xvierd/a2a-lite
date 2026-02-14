import { describe, it, expect, vi } from 'vitest';
import { Agent, AgentTestClient } from '../src/index.js';
import { loggingMiddleware, rateLimitMiddleware, errorHandlingMiddleware } from '../src/middleware/index.js';

describe('Built-in Middlewares', () => {
  describe('Logging Middleware', () => {
    it('should log skill calls', async () => {
      const agent = new Agent({ name: 'Bot', description: 'Test' });
      const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

      agent.use(loggingMiddleware());
      agent.skill('greet', async ({ name }: { name: string }) => {
        return `Hello, ${name}!`;
      });

      const client = new AgentTestClient(agent);
      await client.call('greet', { name: 'World' });

      expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('greet'));
      consoleSpy.mockRestore();
    });

    it('should log successful results', async () => {
      const agent = new Agent({ name: 'Bot', description: 'Test' });
      const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

      agent.use(loggingMiddleware());
      agent.skill('test', async () => 'success');

      const client = new AgentTestClient(agent);
      await client.call('test', {});

      expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('completed'));
      consoleSpy.mockRestore();
    });

    it('should log errors', async () => {
      const agent = new Agent({ name: 'Bot', description: 'Test' });
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      agent.use(loggingMiddleware());
      agent.skill('fail', async () => {
        throw new Error('Test error');
      });

      const client = new AgentTestClient(agent);
      await client.call('fail', {});

      // The error is caught by middleware and logged
      expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('Test error'));
      consoleSpy.mockRestore();
    });

    it('should accept custom logger', async () => {
      const agent = new Agent({ name: 'Bot', description: 'Test' });
      const customLogger = { info: vi.fn(), error: vi.fn() };

      agent.use(loggingMiddleware({ logger: customLogger as any }));
      agent.skill('test', async () => 'result');

      const client = new AgentTestClient(agent);
      await client.call('test', {});

      expect(customLogger.info).toHaveBeenCalled();
    });
  });

  describe('Rate Limit Middleware', () => {
    it('should allow requests within limit', async () => {
      const agent = new Agent({ name: 'Bot', description: 'Test' });

      agent.use(rateLimitMiddleware({ requestsPerMinute: 10 }));
      agent.skill('test', async () => 'ok');

      const client = new AgentTestClient(agent);
      const result = await client.call('test', {});

      expect(result.data).toBe('ok');
    });

    it('should block requests over limit', async () => {
      const agent = new Agent({ name: 'Bot', description: 'Test' });

      agent.use(rateLimitMiddleware({ requestsPerMinute: 2 }));
      agent.skill('test', async () => 'ok');

      const client = new AgentTestClient(agent);

      // First 2 requests should succeed
      const r1 = await client.call('test', {});
      expect(r1.data).toBe('ok');
      const r2 = await client.call('test', {});
      expect(r2.data).toBe('ok');

      // Third request should fail with rate limit error
      const r3 = await client.call('test', {});
      expect(r3.data).toEqual(expect.objectContaining({
        error: expect.stringContaining('Rate limit exceeded'),
      }));
    });

    it('should reset after window', async () => {
      const agent = new Agent({ name: 'Bot', description: 'Test' });

      agent.use(rateLimitMiddleware({ requestsPerMinute: 1, windowMs: 50 }));
      agent.skill('test', async () => 'ok');

      const client = new AgentTestClient(agent);

      // First request succeeds
      const r1 = await client.call('test', {});
      expect(r1.data).toBe('ok');

      // Second request fails
      const r2 = await client.call('test', {});
      expect(r2.data).toEqual(expect.objectContaining({
        error: expect.stringContaining('Rate limit exceeded'),
      }));

      // Wait for window to reset
      await new Promise((resolve) => setTimeout(resolve, 60));

      // Third request should succeed again
      const r3 = await client.call('test', {});
      expect(r3.data).toBe('ok');
    });

    it('should use custom error message', async () => {
      const agent = new Agent({ name: 'Bot', description: 'Test' });

      agent.use(rateLimitMiddleware({
        requestsPerMinute: 1,
        errorMessage: 'Custom rate limit message',
      }));
      agent.skill('test', async () => 'ok');

      const client = new AgentTestClient(agent);
      await client.call('test', {});

      const result = await client.call('test', {});
      expect(result.data).toEqual(expect.objectContaining({
        error: 'Custom rate limit message',
      }));
    });
  });

  describe('Error Handling Middleware', () => {
    it('should catch and format errors', async () => {
      const agent = new Agent({ name: 'Bot', description: 'Test' });

      agent.use(errorHandlingMiddleware());
      agent.skill('fail', async () => {
        throw new Error('Something went wrong');
      });

      const client = new AgentTestClient(agent);
      const result = await client.call('fail', {});

      expect(result.data).toEqual(expect.objectContaining({
        error: expect.stringContaining('Something went wrong'),
      }));
    });

    it('should include error type', async () => {
      const agent = new Agent({ name: 'Bot', description: 'Test' });

      agent.use(errorHandlingMiddleware());
      agent.skill('fail', async () => {
        throw new TypeError('Type mismatch');
      });

      const client = new AgentTestClient(agent);
      const result = await client.call('fail', {});

      expect(result.data).toEqual(expect.objectContaining({
        type: 'TypeError',
      }));
    });

    it('should use custom error handler', async () => {
      const agent = new Agent({ name: 'Bot', description: 'Test' });
      const customHandler = vi.fn().mockReturnValue({ custom: true });

      agent.use(errorHandlingMiddleware({ onError: customHandler }));
      agent.skill('fail', async () => {
        throw new Error('Test');
      });

      const client = new AgentTestClient(agent);
      await client.call('fail', {});

      expect(customHandler).toHaveBeenCalled();
    });

    it('should pass through successful results', async () => {
      const agent = new Agent({ name: 'Bot', description: 'Test' });

      agent.use(errorHandlingMiddleware());
      agent.skill('success', async () => ({ ok: true }));

      const client = new AgentTestClient(agent);
      const result = await client.call('success', {});

      expect(result.data).toEqual({ ok: true });
    });
  });

  describe('Middleware Chaining', () => {
    it('should execute middleware in order', async () => {
      const agent = new Agent({ name: 'Bot', description: 'Test' });
      const order: string[] = [];

      agent.use(async (ctx, next) => {
        order.push('first-before');
        const result = await next();
        order.push('first-after');
        return result;
      });

      agent.use(async (ctx, next) => {
        order.push('second-before');
        const result = await next();
        order.push('second-after');
        return result;
      });

      agent.skill('test', async () => {
        order.push('handler');
        return 'done';
      });

      const client = new AgentTestClient(agent);
      await client.call('test', {});

      expect(order).toEqual([
        'first-before',
        'second-before',
        'handler',
        'second-after',
        'first-after',
      ]);
    });
  });
});
