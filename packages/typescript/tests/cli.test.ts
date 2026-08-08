/**
 * Tests for the a2a-lite CLI (src/cli.ts), executed via tsx.
 *
 * NOTE: runCli is async (execFile, not execFileSync) so the in-process mock
 * HTTP server used by the 0.3-detection tests can keep serving requests.
 */
import { execFile } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, existsSync } from 'node:fs';
import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { promisify } from 'node:util';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

const execFileAsync = promisify(execFile);

const PKG_ROOT = resolve(__dirname, '..');

async function runCli(...cliArgs: string[]): Promise<{ code: number; output: string }> {
  try {
    const { stdout, stderr } = await execFileAsync('npx', ['tsx', 'src/cli.ts', ...cliArgs], {
      cwd: PKG_ROOT,
    });
    return { code: 0, output: `${stdout}${stderr}` };
  } catch (err) {
    const e = err as { code?: number; stdout?: string; stderr?: string };
    return { code: e.code ?? 1, output: `${e.stdout ?? ''}${e.stderr ?? ''}` };
  }
}

describe('CLI doctor', () => {
  it('reports versions and exits 0 in a healthy environment', async () => {
    const { code, output } = await runCli('doctor');
    expect(code).toBe(0);
    expect(output).toContain('a2a-lite:');
    expect(output).toContain('@a2a-js/sdk:');
    expect(output).toContain('Node.js:');
    expect(output).toContain('OK @a2a-js/sdk');
  });
});

describe('CLI init', () => {
  let dir: string;

  beforeAll(() => {
    dir = mkdtempSync(join(tmpdir(), 'a2a-lite-cli-'));
  });

  afterAll(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it('scaffolds a project with a2a-lite >=1.0.0', async () => {
    const target = join(dir, 'my-agent');
    const { code } = await runCli('init', target);
    expect(code).toBe(0);

    const pkg = JSON.parse(readFileSync(join(target, 'package.json'), 'utf8'));
    expect(pkg.dependencies['a2a-lite']).toBe('>=1.0.0');

    const agentTs = readFileSync(join(target, 'agent.ts'), 'utf8');
    expect(agentTs).toContain("import { Agent } from 'a2a-lite'");
    expect(agentTs).toContain('agent.skill(');
    expect(existsSync(join(target, '.gitignore'))).toBe(true);
  });
});

describe('CLI 0.3 detection', () => {
  let server: Server;
  let baseUrl: string;

  const v03Card = {
    name: 'LegacyBot',
    url: 'http://localhost/',
    protocolVersion: '0.3.0',
    version: '1.0.0',
    capabilities: {},
    skills: [],
  };

  beforeAll(async () => {
    server = createServer((req, res) => {
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify(v03Card));
    });
    await new Promise<void>((resolveListen) => server.listen(0, '127.0.0.1', resolveListen));
    const { port } = server.address() as AddressInfo;
    baseUrl = `http://127.0.0.1:${port}`;
  });

  afterAll(async () => {
    await new Promise<void>((resolveClose) => server.close(() => resolveClose()));
  });

  it.each(['inspect', 'info'])('%s rejects 0.3 agents with a clear message', async (cmd) => {
    const { code, output } = await runCli(cmd, baseUrl);
    expect(code).toBe(1);
    expect(output).toContain('This agent speaks A2A 0.3');
    expect(output).toContain('requires protocol v1.0');
  });

  it('test rejects 0.3 agents with a clear message', async () => {
    const { code, output } = await runCli('test', baseUrl, 'hello');
    expect(code).toBe(1);
    expect(output).toContain('This agent speaks A2A 0.3');
  });

  it('discover reports 0.3 agents as failures without crashing', async () => {
    const { code, output } = await runCli('discover', baseUrl);
    expect(code).toBe(0);
    expect(output).toContain('This agent speaks A2A 0.3');
  });

  it('doctor rejects a 0.3 remote agent', async () => {
    const { code, output } = await runCli('doctor', baseUrl);
    expect(code).toBe(1);
    expect(output).toContain('This agent speaks A2A 0.3');
  });
});
