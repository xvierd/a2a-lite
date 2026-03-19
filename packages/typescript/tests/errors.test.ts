import { describe, it, expect } from 'vitest';
import {
  A2ALiteError,
  SkillNotFoundError,
  ParamValidationError,
  RemoteAgentError,
  AuthRequiredError,
} from '../src/errors.js';

// ---------------------------------------------------------------------------
// A2ALiteError (base class)
// ---------------------------------------------------------------------------

describe('A2ALiteError', () => {
  it('sets the message correctly', () => {
    const err = new A2ALiteError('something went wrong');
    expect(err.message).toBe('something went wrong');
  });

  it('sets the name to the constructor name', () => {
    const err = new A2ALiteError('test');
    expect(err.name).toBe('A2ALiteError');
  });

  it('is an instance of Error', () => {
    const err = new A2ALiteError('test');
    expect(err).toBeInstanceOf(Error);
  });

  it('toResponse returns error and type', () => {
    const err = new A2ALiteError('boom');
    expect(err.toResponse()).toEqual({
      error: 'boom',
      type: 'A2ALiteError',
    });
  });
});

// ---------------------------------------------------------------------------
// SkillNotFoundError
// ---------------------------------------------------------------------------

describe('SkillNotFoundError', () => {
  it('includes skill name in message', () => {
    const err = new SkillNotFoundError('doStuff');
    expect(err.message).toContain("Unknown skill 'doStuff'");
  });

  it('stores the skill name', () => {
    const err = new SkillNotFoundError('doStuff');
    expect(err.skill).toBe('doStuff');
  });

  it('defaults availableSkills to empty array', () => {
    const err = new SkillNotFoundError('x');
    expect(err.availableSkills).toEqual([]);
  });

  it('lists available skills in message when provided', () => {
    const err = new SkillNotFoundError('x', ['a', 'b']);
    expect(err.message).toContain('Available skills: a, b');
  });

  it('is an instance of A2ALiteError', () => {
    const err = new SkillNotFoundError('x');
    expect(err).toBeInstanceOf(A2ALiteError);
  });

  it('toResponse includes available_skills', () => {
    const err = new SkillNotFoundError('foo', ['bar', 'baz']);
    const resp = err.toResponse();
    expect(resp.type).toBe('SkillNotFoundError');
    expect(resp.available_skills).toEqual(['bar', 'baz']);
    expect(resp.error).toContain('foo');
  });
});

// ---------------------------------------------------------------------------
// ParamValidationError
// ---------------------------------------------------------------------------

describe('ParamValidationError', () => {
  const errors = [
    { field: 'name', message: 'is required' },
    { field: 'age', message: 'must be a number' },
  ];

  it('stores skill and errors', () => {
    const err = new ParamValidationError('greet', errors);
    expect(err.skill).toBe('greet');
    expect(err.errors).toEqual(errors);
  });

  it('includes each field error in the message', () => {
    const err = new ParamValidationError('greet', errors);
    expect(err.message).toContain("'name': is required");
    expect(err.message).toContain("'age': must be a number");
  });

  it('handles errors without field or message', () => {
    const err = new ParamValidationError('x', [{}]);
    expect(err.message).toContain("'unknown': validation failed");
  });

  it('toResponse includes validation_errors and skill', () => {
    const err = new ParamValidationError('greet', errors);
    const resp = err.toResponse();
    expect(resp.type).toBe('ParamValidationError');
    expect(resp.skill).toBe('greet');
    expect(resp.validation_errors).toEqual(errors);
  });

  it('is an instance of A2ALiteError', () => {
    const err = new ParamValidationError('x', []);
    expect(err).toBeInstanceOf(A2ALiteError);
  });
});

// ---------------------------------------------------------------------------
// RemoteAgentError
// ---------------------------------------------------------------------------

describe('RemoteAgentError', () => {
  it('stores message and response', () => {
    const err = new RemoteAgentError('failed', { status: 500 });
    expect(err.message).toBe('failed');
    expect(err.response).toEqual({ status: 500 });
  });

  it('defaults response to empty object', () => {
    const err = new RemoteAgentError('oops');
    expect(err.response).toEqual({});
  });

  it('toResponse includes remote_response', () => {
    const err = new RemoteAgentError('err', { code: 42 });
    const resp = err.toResponse();
    expect(resp.type).toBe('RemoteAgentError');
    expect(resp.remote_response).toEqual({ code: 42 });
  });

  it('is an instance of A2ALiteError', () => {
    const err = new RemoteAgentError('x');
    expect(err).toBeInstanceOf(A2ALiteError);
  });
});

// ---------------------------------------------------------------------------
// AuthRequiredError
// ---------------------------------------------------------------------------

describe('AuthRequiredError', () => {
  it('uses default scheme when none provided', () => {
    const err = new AuthRequiredError();
    expect(err.message).toContain('authentication');
    expect(err.schemeInfo).toBe('authentication');
  });

  it('includes custom scheme in message', () => {
    const err = new AuthRequiredError('OAuth2');
    expect(err.message).toContain('OAuth2');
    expect(err.schemeInfo).toBe('OAuth2');
  });

  it('includes detail in message when provided', () => {
    const err = new AuthRequiredError('Bearer', 'Token expired');
    expect(err.message).toContain('Token expired');
    expect(err.detail).toBe('Token expired');
  });

  it('detail is undefined when not provided', () => {
    const err = new AuthRequiredError('Bearer');
    expect(err.detail).toBeUndefined();
  });

  it('toResponse includes scheme', () => {
    const err = new AuthRequiredError('Bearer', 'details here');
    const resp = err.toResponse();
    expect(resp.type).toBe('AuthRequiredError');
    expect(resp.scheme).toBe('Bearer');
    expect(resp.detail).toBe('details here');
    expect(resp.error).toBe('Authentication required');
  });

  it('toResponse omits detail when absent', () => {
    const err = new AuthRequiredError('Bearer');
    const resp = err.toResponse();
    expect(resp.detail).toBeUndefined();
  });

  it('is an instance of A2ALiteError', () => {
    const err = new AuthRequiredError();
    expect(err).toBeInstanceOf(A2ALiteError);
  });
});
