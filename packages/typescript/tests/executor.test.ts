import { describe, it, expect, vi, beforeEach } from 'vitest';
import { LiteAgentExecutor } from '../src/executor.js';
import { A2ALiteError } from '../src/errors.js';
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
    taskId: 'task-1',
    userMessage: {
      parts: [{ content: { $case: 'text' as const, value: text } }],
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

/** Extract the text of the first part of a published AgentExecutionEvent. */
function publishedText(bus: ReturnType<typeof makeEventBus>, callIndex = 0): string {
  const event = (bus.publish as ReturnType<typeof vi.fn>).mock.calls[callIndex][0];
  const part = event.data.parts[0];
  return part.content.$case === 'text' ? part.content.value : '';
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
    expect(publishedText(bus)).toContain('SkillNotFoundError');
    expect(bus.finished).toHaveBeenCalled();
  });

  it('publishes error for an unknown skill name', async () => {
    skills.set('echo', makeSkill());
    const executor = new LiteAgentExecutor({ skills });

    const ctx = makeRequestContext(JSON.stringify({ skill: 'missing' }));
    const bus = makeEventBus();

    await executor.execute(ctx, bus);

    expect(publishedText(bus)).toContain('SkillNotFoundError');
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

    expect(publishedText(bus)).toContain('handler exploded');
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
    expect(publishedText(bus)).toContain('"custom":true');
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

    const parsed = JSON.parse(publishedText(bus));
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

    expect(JSON.parse(publishedText(bus))).toEqual({ answer: 42 });
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

    expect(publishedText(bus)).toBe('123');
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
// Streaming — A2A v1.0 event rules (first event must be the task)
// ---------------------------------------------------------------------------

describe('LiteAgentExecutor streaming', () => {
  it('publishes task first, then working status updates, then completion', async () => {
    const skill = makeSkill({
      isStreaming: true,
      handler: vi.fn(async function* () {
        yield 'chunk-1';
        yield 'chunk-2';
      }) as unknown as SkillDefinition['handler'],
    });
    const skills = new Map([['stream', skill]]);
    const executor = new LiteAgentExecutor({ skills });

    const ctx = makeRequestContext(JSON.stringify({ skill: 'stream' }));
    const bus = makeEventBus();

    await executor.execute(ctx, bus);

    const events = (bus.publish as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0]);

    // First event: the task
    expect(events[0].kind).toBe('task');
    expect(events[0].data.id).toBe('task-1');
    expect(events[0].data.contextId).toBe('ctx-1');

    // Then: working (start) + one working status per chunk
    expect(events[1].kind).toBe('statusUpdate');
    expect(events[1].data.status.state).toBe(2); // TASK_STATE_WORKING
    expect(events[2].kind).toBe('statusUpdate');
    expect(events[2].data.status.message.parts[0].content.value).toBe('chunk-1');
    expect(events[3].data.status.message.parts[0].content.value).toBe('chunk-2');

    // Final: completed terminal status
    const last = events[events.length - 1];
    expect(last.kind).toBe('statusUpdate');
    expect(last.data.status.state).toBe(3); // TASK_STATE_COMPLETED

    expect(bus.finished).toHaveBeenCalled();
  });

  it('publishes a failed status update when a streaming skill throws mid-stream', async () => {
    const skill = makeSkill({
      isStreaming: true,
      handler: vi.fn(async function* () {
        yield 'first';
        throw new Error('stream exploded');
      }) as unknown as SkillDefinition['handler'],
    });
    const skills = new Map([['stream', skill]]);
    const executor = new LiteAgentExecutor({ skills });

    const ctx = makeRequestContext(JSON.stringify({ skill: 'stream' }));
    const bus = makeEventBus();

    await executor.execute(ctx, bus);

    const events = (bus.publish as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0]);
    expect(events[0].kind).toBe('task');
    const last = events[events.length - 1];
    expect(last.kind).toBe('statusUpdate');
    expect(last.data.status.state).toBe(4); // TASK_STATE_FAILED
    expect(last.data.status.message.parts[0].content.value).toContain('stream exploded');
    expect(bus.finished).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// cancelTask
// ---------------------------------------------------------------------------

describe('LiteAgentExecutor.cancelTask()', () => {
  it('publishes a cancellation acknowledgement message and finishes', async () => {
    const executor = new LiteAgentExecutor({ skills: new Map() });
    const bus = makeEventBus();
    await executor.cancelTask('task-9', bus);

    expect(bus.publish).toHaveBeenCalledTimes(1);
    const event = (bus.publish as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(event.kind).toBe('message');
    expect(publishedText(bus)).toContain('cancelled');
    expect(bus.finished).toHaveBeenCalled();
  });
});
