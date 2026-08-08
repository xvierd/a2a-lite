/**
 * Structured error types for A2A Lite TypeScript.
 * Mirrors Python's errors.py for cross-language consistency.
 */

export class A2ALiteError extends Error {
  constructor(message: string) {
    super(message);
    this.name = this.constructor.name;
  }

  toResponse(): Record<string, unknown> {
    return { error: this.message, type: this.name };
  }
}

export class SkillNotFoundError extends A2ALiteError {
  readonly skill: string;
  readonly availableSkills: string[];

  constructor(skill: string, availableSkills: string[] = []) {
    const available = availableSkills.length > 0 ? `\nAvailable skills: ${availableSkills.join(', ')}` : '';
    super(`Unknown skill '${skill}'.${available}`);
    this.skill = skill;
    this.availableSkills = availableSkills;
  }

  toResponse(): Record<string, unknown> {
    return {
      error: `Unknown skill '${this.skill}'`,
      type: 'SkillNotFoundError',
      available_skills: this.availableSkills,
    };
  }
}

export class ParamValidationError extends A2ALiteError {
  readonly skill: string;
  readonly errors: Array<Record<string, unknown>>;

  constructor(skill: string, errors: Array<Record<string, unknown>>) {
    const msgs = errors.map((e) => `  - '${e.field ?? 'unknown'}': ${e.message ?? 'validation failed'}`);
    super(`Skill '${skill}' parameter error:\n${msgs.join('\n')}`);
    this.skill = skill;
    this.errors = errors;
  }

  toResponse(): Record<string, unknown> {
    return {
      error: `Skill '${this.skill}' parameter validation failed`,
      type: 'ParamValidationError',
      skill: this.skill,
      validation_errors: this.errors,
    };
  }
}

export class RemoteAgentError extends A2ALiteError {
  readonly response: Record<string, unknown>;

  constructor(message: string, response?: Record<string, unknown>) {
    super(message);
    this.response = response ?? {};
  }

  toResponse(): Record<string, unknown> {
    return {
      error: this.message,
      type: 'RemoteAgentError',
      remote_response: this.response,
    };
  }
}

export class AuthRequiredError extends A2ALiteError {
  readonly schemeInfo: string;
  readonly detail?: string;

  constructor(schemeInfo?: string, detail?: string) {
    const scheme = schemeInfo ?? 'authentication';
    const msg = `Authentication required. This agent uses ${scheme}.${detail ? `\n${detail}` : ''}`;
    super(msg);
    this.schemeInfo = scheme;
    this.detail = detail;
  }

  toResponse(): Record<string, unknown> {
    const resp: Record<string, unknown> = {
      error: 'Authentication required',
      type: 'AuthRequiredError',
      scheme: this.schemeInfo,
    };
    if (this.detail) resp.detail = this.detail;
    return resp;
  }
}
