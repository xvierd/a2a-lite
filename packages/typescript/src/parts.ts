/**
 * Multi-modal parts support (Text, File, Data).
 *
 * Optional - only import if you need files or structured data.
 *
 * Example (simple - no parts needed):
 *   agent.skill("greet", async ({ name }) => `Hello, ${name}!`);
 *
 * Example (with files):
 *   import { FilePart } from 'a2a-lite';
 *
 *   agent.skill("summarize", async ({ doc }: { doc: FilePart }) => {
 *     const content = await doc.readText();
 *     return `Summary: ${content.slice(0, 100)}...`;
 *   });
 */

import { readFileSync } from 'fs';
import { basename } from 'path';
import type { LiteTextPart, LiteFilePart, LiteDataPart, LitePart, Artifact as IArtifact } from './types.js';

/**
 * Create a text part.
 */
export function textPart(text: string): LiteTextPart {
  return { type: 'text', text };
}

/**
 * File part with helper methods.
 */
export class FilePart implements LiteFilePart {
  readonly type = 'file' as const;
  readonly name: string;
  readonly mimeType: string;
  readonly data?: Buffer;
  readonly uri?: string;

  constructor(options: {
    name: string;
    mimeType?: string;
    data?: Buffer | string;
    uri?: string;
  }) {
    this.name = options.name;
    this.mimeType = options.mimeType ?? 'application/octet-stream';
    this.uri = options.uri;

    if (options.data) {
      this.data =
        typeof options.data === 'string' ? Buffer.from(options.data) : options.data;
    }
  }

  /**
   * Create from a local file path.
   */
  static fromPath(path: string, mimeType?: string): FilePart {
    const data = readFileSync(path);
    const name = basename(path);
    const guessedMime = mimeType ?? guessMimeType(name);
    return new FilePart({ name, mimeType: guessedMime, data });
  }

  /**
   * Create from A2A format.
   */
  static fromA2A(data: Record<string, unknown>): FilePart {
    const file = data.file as Record<string, unknown>;
    return new FilePart({
      name: (file.name as string) ?? 'unknown',
      mimeType: (file.mimeType as string) ?? 'application/octet-stream',
      data: file.bytes ? Buffer.from(file.bytes as string, 'base64') : undefined,
      uri: file.uri as string | undefined,
    });
  }

  get isUri(): boolean {
    return this.uri !== undefined;
  }

  get isBytes(): boolean {
    return this.data !== undefined;
  }

  /**
   * Read file content as string.
   */
  async readText(encoding: BufferEncoding = 'utf-8'): Promise<string> {
    const bytes = await this.readBytes();
    return bytes.toString(encoding);
  }

  /**
   * Read file content as bytes.
   */
  async readBytes(): Promise<Buffer> {
    if (this.data) {
      return this.data;
    }

    if (this.uri) {
      const response = await fetch(this.uri);
      const arrayBuffer = await response.arrayBuffer();
      return Buffer.from(arrayBuffer);
    }

    throw new Error('FilePart has no data or URI');
  }

  /**
   * Convert to A2A format.
   */
  toA2A(): Record<string, unknown> {
    if (this.uri) {
      return {
        type: 'file',
        kind: 'file',
        file: {
          name: this.name,
          mimeType: this.mimeType,
          uri: this.uri,
        },
      };
    }

    return {
      type: 'file',
      kind: 'file',
      file: {
        name: this.name,
        mimeType: this.mimeType,
        bytes: this.data?.toString('base64') ?? '',
      },
    };
  }
}

/**
 * Structured data part.
 */
export class DataPart implements LiteDataPart {
  readonly type = 'data' as const;
  readonly data: Record<string, unknown>;

  constructor(data: Record<string, unknown>) {
    this.data = data;
  }

  static fromA2A(raw: Record<string, unknown>): DataPart {
    return new DataPart((raw.data as Record<string, unknown>) ?? {});
  }

  toA2A(): Record<string, unknown> {
    return {
      type: 'data',
      kind: 'data',
      data: this.data,
    };
  }
}

/**
 * Rich output artifact.
 *
 * Example:
 *   const artifact = new Artifact({ name: "report" })
 *     .addText("Summary here")
 *     .addData({ count: 42 })
 *     .addFile(FilePart.fromPath("data.csv"));
 */
export class Artifact implements IArtifact {
  name?: string;
  description?: string;
  parts: LitePart[] = [];
  metadata?: Record<string, unknown>;

  constructor(options?: {
    name?: string;
    description?: string;
    metadata?: Record<string, unknown>;
  }) {
    this.name = options?.name;
    this.description = options?.description;
    this.metadata = options?.metadata;
  }

  addText(text: string): this {
    this.parts.push(textPart(text));
    return this;
  }

  addFile(file: FilePart): this {
    this.parts.push(file);
    return this;
  }

  addData(data: Record<string, unknown>): this {
    this.parts.push(new DataPart(data));
    return this;
  }

  toA2A(): Record<string, unknown> {
    return {
      name: this.name,
      description: this.description,
      parts: this.parts.map((p) => {
        if ('toA2A' in p && typeof p.toA2A === 'function') {
          return p.toA2A();
        }
        return p;
      }),
      metadata: this.metadata,
    };
  }
}

/**
 * Parse an A2A part.
 */
export function parsePart(data: Record<string, unknown>): LitePart {
  const partKind = (data.kind ?? data.type) as string;

  switch (partKind) {
    case 'text':
      return { type: 'text', text: (data.text as string) ?? '' };
    case 'file':
      return FilePart.fromA2A(data);
    case 'data':
      return DataPart.fromA2A(data);
    default:
      return { type: 'text', text: String(data) };
  }
}

/**
 * Guess mime type from filename.
 */
function guessMimeType(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase();

  const mimeTypes: Record<string, string> = {
    txt: 'text/plain',
    html: 'text/html',
    css: 'text/css',
    js: 'application/javascript',
    ts: 'application/typescript',
    json: 'application/json',
    xml: 'application/xml',
    pdf: 'application/pdf',
    png: 'image/png',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    gif: 'image/gif',
    svg: 'image/svg+xml',
    csv: 'text/csv',
    md: 'text/markdown',
  };

  return mimeTypes[ext ?? ''] ?? 'application/octet-stream';
}
