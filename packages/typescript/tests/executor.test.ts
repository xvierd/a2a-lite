import { describe, it, expect, vi, beforeEach } from 'vitest';
import { LiteAgentExecutor } from '../src/executor.js';
import { SkillNotFoundError, A2ALiteError } from '../src/errors.js';
import type { SkillDefinition } from '../src/types.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSkill(overrides: Partial<SkillDefinition> = {}): SkillDefinition {
  return {
    name: 'echo',
    description: 'Echo skill',
    tags: [],
    handler: vi.fn(async (params: Record<string, unknown>) => params.message ?? 'default'),
    inputSchema: {},
    outputSchema: {},
    isStreaming: false,
    needsTaskContext: false,
    needsInteraction: false,
    needsMcp: false,
    ...overrides,
  };
}

function makeRequestContext(text: string, contextId = 'ctx-1') {
  return {
    contextId,
    userMessage: {
      parts: [{ kind: 'text' as const, text }],
    },
  } as unknown as import('@a2a-js/sdk/server').RequestContext;
}

function makeEventBus() {
  return {
    publish: vi.fn(),
    finished: vi.fn(),
    subscribe: vi.fn(),
  } as unknown as import('@a2a-js/sdk/server').ExecutionEventBus;
}

// ---------------------------------------------------------------------------
// Skill execution
// ---------------------------------------------------------------------------

describe('LiteAgentExecutor', () => {
  let skills: Map<string, SkillDefinition>;

  beforeEach(() => {
    skills = new Map();
  });

  it('executes a skill by name from JSON message', async () => {
    const skill = makeSkill();
    skills.set('echo', skill);
    const executor = new LiteAgentExecutor({ skills });

    const ctx = makeRequestContext(JSON.stringify({ skill: 'echo', params: { message: 'hi' } }));
    const bus = makeEventBus();

    await executor.execute(ctx, bus);

    expect(skill.handler).toHaveBeenCalledWith(expect.objectContaining({ message: 'hi' }));
    expect(bus.publish).toHaveBeenCalled();
    expect(bus.finished).toHaveBeenCalled();
  });

  it('defaults to single skill when no skill name in message', async () => {
    const skill = makeSkill();
    skills.set('only', skill);
    const executor = new LiteAgentExecutor({ skills });

    const ctx = makeRequestContext('hello world');
    const bus = makeEventBus();

    await executor.execute(ctx, bus);

    expect(skill.handler).toHaveBeenCalled();
    expect(bus.finished).toHaveBeenCalled();
  });

  it('publishes error when skill is not found', async () => {
    skills.set('a', makeSkill({ name: 'a' }));
    skills.set('b', makeSkill({ name: 'b' }));
    const executor = new LiteAgentExecutor({ skills });

    const ctx = makeRequestContext('plain text with multiple skills');
    const bus = makeEventBus();

    await executor.execute(ctx, bus);

    // With multiple skills and no skill name, it should error
    expect(bus.publish).toHaveBeenCalled();
    const publishedMsg = (bus.publish as ReturnType<typeof vi.fn>).mock.calls[0][0];
    const text = publishedMsg.parts[0].text;
    expect(text).toContain('SkillNotFoundError');
    expect(bus.finished).toHaveBeenCalled();
  });

  it('publishes error for an unknown skill name', async () => {
    skills.set('echo', makeSkill());
    const executor = new LiteAgentExecutor({ skills });

    const ctx = makeRequestContext(JSON.stringify({ skill: 'missing' }));
    const bus = makeEventBus();

    await executor.execute(ctx, bus);

    const publishedMsg = (bus.publish as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(publishedMsg.parts[0].text).toContain('SkillNotFoundError');
  });

  it('publishes error when skill handler throws', async () => {
    const skill = makeSkill({
      handler: vi.fn(async () => {
        throw new Error('handler exploded');
      }),
    });
    skills.set('boom', skill);
    const executor = new LiteAgentExecutor({ skills });

    const ctx = makeRequestContext(JSON.stringify({ skill: 'boom' }));
    const bus = makeEventBus();

    await executor.execute(ctx, bus);

    const publishedMsg = (bus.publish as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(publishedMsg.parts[0].text).toContain('handler exploded');
    expect(bus.finished).toHaveBeenCalled();
  });

  it('uses custom error handler when provided', async () => {
    const skill = makeSkill({
      handler: vi.fn(async () => {
        throw new Error('oops');
      }),
    });
    skills.set('fail', skill);

    const errorHandler = vi.fn(async (err: Error) => ({
      custom: true,
      msg: err.message,
    }));
    const executor = new LiteAgentExecutor({ skills, errorHandler });

    const ctx = makeRequestContext(JSON.stringify({ skill: 'fail' }));
    const bus = makeEventBus();

    await executor.execute(ctx, bus);

    expect(errorHandler).toHaveBeenCalled();
    const publishedMsg = (bus.publish as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(publishedMsg.parts[0].text).toContain('"custom":true');
  });

  it('formats A2ALiteError using toResponse()', async () => {
    const skill = makeSkill({
      handler: vi.fn(async () => {
        throw new A2ALiteError('a2a error');
      }),
    });
    skills.set('a2a', skill);
    const executor = new LiteAgentExecutor({ skills });

    const ctx = makeRequestContext(JSON.stringify({ skill: 'a2a' }));
    const bus = makeEventBus();

    await executor.execute(ctx, bus);

    const publishedMsg = (bus.publish as ReturnType<typeof vi.fn>).mock.calls[0][0];
    const parsed = JSON.parse(publishedMsg.parts[0].text);
    expect(parsed.type).toBe('A2ALiteError');
    expect(parsed.error).toBe('a2a error');
  });

  it('stringifies object results as JSON', async () => {
    const skill = makeSkill({
      handler: vi.fn(async () => ({ answer: 42 })),
    });
    skills.set('calc', skill);
    const executor = new LiteAgentExecutor({ skills });

    const ctx = makeRequestContext(JSON.stringify({ skill: 'calc' }));
    const bus = makeEventBus();

    await executor.execute(ctx, bus);

    const publishedMsg = (bus.publish as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(JSON.parse(publishedMsg.parts[0].text)).toEqual({ answer: 42 });
  });

  it('converts non-object results to string', async () => {
    const skill = makeSkill({
      handler: vi.fn(async () => 123),
    });
    skills.set('num', skill);
    const executor = new LiteAgentExecutor({ skills });

    const ctx = makeRequestContext(JSON.stringify({ skill: 'num' }));
    const bus = makeEventBus();

    await executor.execute(ctx, bus);

    const publishedMsg = (bus.publish as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(publishedMsg.parts[0].text).toBe('123');
  });
});

// ---------------------------------------------------------------------------
// Middleware chain
// ---------------------------------------------------------------------------

describe('LiteAgentExecutor middleware', () => {
  it('runs middleware in order around skill execution', async () => {
    const order: string[] = [];
    const skill = makeSkill({
      handler: vi.fn(async () => {
        order.push('handler');
        return 'ok';
      }),
    });
    const skills = new Map([['test', skill]]);

    const middleware = vi.fn(async (ctx, next) => {
      order.push('before');
      const result = await next();
      order.push('after');
      return result;
    });

    const executor = new LiteAgentExecutor({ skills, middlewares: [middleware] });
    const ctx = makeRequestContext(JSON.stringify({ skill: 'test' }));
    const bus = makeEventBus();

    await executor.execute(ctx, bus);

    expect(order).toEqual(['before', 'handler', 'after']);
  });
});

// ---------------------------------------------------------------------------
// Completion hooks
// ---------------------------------------------------------------------------

describe('LiteAgentExecutor completion hooks', () => {
  it('calls onComplete hooks after successful execution', async () => {
    const hookFn = vi.fn();
    const skill = makeSkill({ handler: vi.fn(async () => 'result') });
    const skills = new Map([['test', skill]]);

    const executor = new LiteAgentExecutor({ skills, onCompleteHooks: [hookFn] });
    const ctx = makeRequestContext(JSON.stringify({ skill: 'test' }));
    const bus = makeEventBus();

    await executor.execute(ctx, bus);

    expect(hookFn).toHaveBeenCalledWith('test', 'result');
  });

  it('continues even if a hook throws', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const badHook = vi.fn(() => {
      throw new Error('hook failed');
    });
    const skill = makeSkill({ handler: vi.fn(async () => 'ok') });
    const skills = new Map([['test', skill]]);

    const executor = new LiteAgentExecutor({ skills, onCompleteHooks: [badHook] });
    const ctx = makeRequestContext(JSON.stringify({ skill: 'test' }));
    const bus = makeEventBus();

    await executor.execute(ctx, bus);

    expect(bus.finished).toHaveBeenCalled();
    vi.restoreAllMocks();
  });
});

// ---------------------------------------------------------------------------
// cancelTask
// ---------------------------------------------------------------------------

describe('LiteAgentExecutor.cancelTask()', () => {
  it('resolves without error (no-op)', async () => {
    const executor = new LiteAgentExecutor({ skills: new Map() });
    await expect(executor.cancelTask()).resolves.toBeUndefined();
  });
});
