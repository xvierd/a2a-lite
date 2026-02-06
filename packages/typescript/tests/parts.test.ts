import { describe, it, expect } from 'vitest';
import { FilePart, DataPart, Artifact, textPart, parsePart } from '../src/parts.js';

describe('textPart', () => {
  it('should create a text part', () => {
    const part = textPart('Hello, world!');
    expect(part.type).toBe('text');
    expect(part.text).toBe('Hello, world!');
  });
});

describe('FilePart', () => {
  it('should create with bytes', () => {
    const part = new FilePart({
      name: 'test.txt',
      mimeType: 'text/plain',
      data: Buffer.from('Hello, world!'),
    });

    expect(part.name).toBe('test.txt');
    expect(part.isBytes).toBe(true);
    expect(part.isUri).toBe(false);
  });

  it('should create with string data', () => {
    const part = new FilePart({
      name: 'test.txt',
      data: 'Hello, world!',
    });

    expect(part.isBytes).toBe(true);
    expect(part.data?.toString()).toBe('Hello, world!');
  });

  it('should create with URI', () => {
    const part = new FilePart({
      name: 'remote.txt',
      uri: 'https://example.com/file.txt',
    });

    expect(part.isUri).toBe(true);
    expect(part.isBytes).toBe(false);
  });

  it('should convert to A2A format with bytes', () => {
    const part = new FilePart({
      name: 'test.txt',
      mimeType: 'text/plain',
      data: Buffer.from('Hello'),
    });

    const a2a = part.toA2A();

    expect(a2a.type).toBe('file');
    expect((a2a.file as any).name).toBe('test.txt');
    expect((a2a.file as any).bytes).toBe(Buffer.from('Hello').toString('base64'));
  });

  it('should convert to A2A format with URI', () => {
    const part = new FilePart({
      name: 'test.txt',
      uri: 'https://example.com/file.txt',
    });

    const a2a = part.toA2A();

    expect(a2a.type).toBe('file');
    expect((a2a.file as any).uri).toBe('https://example.com/file.txt');
  });

  it('should parse from A2A format', () => {
    const a2aData = {
      type: 'file',
      file: {
        name: 'test.txt',
        mimeType: 'text/plain',
        bytes: Buffer.from('Hello').toString('base64'),
      },
    };

    const part = FilePart.fromA2A(a2aData);

    expect(part.name).toBe('test.txt');
    expect(part.data?.toString()).toBe('Hello');
  });

  it('should read bytes', async () => {
    const part = new FilePart({
      name: 'test.txt',
      data: 'Hello',
    });

    const content = await part.readBytes();
    expect(content.toString()).toBe('Hello');
  });

  it('should read text', async () => {
    const part = new FilePart({
      name: 'test.txt',
      data: 'Hello, world!',
    });

    const content = await part.readText();
    expect(content).toBe('Hello, world!');
  });
});

describe('DataPart', () => {
  it('should create with data', () => {
    const part = new DataPart({ key: 'value', count: 42 });
    expect(part.data).toEqual({ key: 'value', count: 42 });
  });

  it('should convert to A2A format', () => {
    const part = new DataPart({ key: 'value' });
    const a2a = part.toA2A();

    expect(a2a.type).toBe('data');
    expect(a2a.data).toEqual({ key: 'value' });
  });

  it('should parse from A2A format', () => {
    const part = DataPart.fromA2A({ type: 'data', data: { key: 'value' } });
    expect(part.data).toEqual({ key: 'value' });
  });
});

describe('Artifact', () => {
  it('should create empty artifact', () => {
    const artifact = new Artifact({ name: 'report.json' });
    expect(artifact.name).toBe('report.json');
    expect(artifact.parts).toEqual([]);
  });

  it('should add text', () => {
    const artifact = new Artifact();
    artifact.addText('Hello');

    expect(artifact.parts).toHaveLength(1);
    expect((artifact.parts[0] as any).text).toBe('Hello');
  });

  it('should add file', () => {
    const artifact = new Artifact();
    const file = new FilePart({ name: 'test.txt', data: 'content' });
    artifact.addFile(file);

    expect(artifact.parts).toHaveLength(1);
    expect((artifact.parts[0] as any).name).toBe('test.txt');
  });

  it('should add data', () => {
    const artifact = new Artifact();
    artifact.addData({ key: 'value' });

    expect(artifact.parts).toHaveLength(1);
    expect((artifact.parts[0] as any).data).toEqual({ key: 'value' });
  });

  it('should support chaining', () => {
    const artifact = new Artifact({ name: 'combined' })
      .addText('Summary')
      .addData({ count: 10 });

    expect(artifact.parts).toHaveLength(2);
  });

  it('should convert to A2A format', () => {
    const artifact = new Artifact({ name: 'report', description: 'Test' });
    artifact.addText('Hello');

    const a2a = artifact.toA2A();

    expect(a2a.name).toBe('report');
    expect(a2a.description).toBe('Test');
    expect((a2a.parts as any[])).toHaveLength(1);
  });
});

describe('parsePart', () => {
  it('should parse text part', () => {
    const part = parsePart({ type: 'text', text: 'Hello' });
    expect(part.type).toBe('text');
    expect((part as any).text).toBe('Hello');
  });

  it('should parse file part', () => {
    const part = parsePart({
      type: 'file',
      file: { name: 'test.txt', bytes: Buffer.from('data').toString('base64') },
    });
    expect(part.type).toBe('file');
  });

  it('should parse data part', () => {
    const part = parsePart({ type: 'data', data: { key: 'value' } });
    expect(part.type).toBe('data');
  });

  it('should handle kind alias', () => {
    const part = parsePart({ kind: 'text', text: 'Hello' });
    expect(part.type).toBe('text');
  });
});
