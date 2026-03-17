#!/usr/bin/env node
/**
 * A2A Lite CLI
 *
 * Usage:
 *   npx a2a-lite init my-agent
 *   npx a2a-lite inspect http://localhost:8787
 *   npx a2a-lite test http://localhost:8787 greet --param name=World
 *   npx a2a-lite discover http://localhost:8787 http://localhost:8788
 */

import { writeFileSync, mkdirSync, existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

const args = process.argv.slice(2);
const command = args[0];

function printHelp(): void {
  console.log(`
A2A Lite CLI v${getVersion()}

Commands:
  init <name>                 Create a new A2A Lite agent project
  inspect <url>               Inspect an agent's capabilities
  test <url> <skill> [opts]   Call a skill and show the result
  discover <url...>           Discover and compare multiple agents

Options:
  --help, -h    Show this help
  --version     Show version
`);
}

function getVersion(): string {
  try {
    const pkg = JSON.parse(
      readFileSync(new URL('../package.json', import.meta.url), 'utf8')
    );
    return pkg.version;
  } catch {
    return '0.2.5';
  }
}

async function cmdInit(name: string): Promise<void> {
  const dir = resolve(name);
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });

  const safeName = name.replace(/[^a-z0-9-]/gi, '-').toLowerCase();

  writeFileSync(
    join(dir, 'agent.ts'),
    `/**
 * ${name} - A2A Lite Agent
 */
import { Agent } from 'a2a-lite';

const agent = new Agent({ name: '${name}', description: 'A simple A2A Lite agent' });

agent.skill('hello', async ({ name = 'World' }: { name?: string }) => {
  return \`Hello, \${name}!\`;
});

agent.skill('echo', async ({ message }: { message: string }) => {
  return { received: message, echoed: true };
});

agent.run();
`
  );

  writeFileSync(
    join(dir, 'package.json'),
    JSON.stringify(
      {
        name: safeName,
        version: '0.1.0',
        type: 'module',
        scripts: { start: 'npx tsx agent.ts', test: 'vitest run' },
        dependencies: { 'a2a-lite': '>=0.2.5', express: '>=4.0.0' },
        devDependencies: { tsx: '>=4.0.0', typescript: '>=5.0.0', vitest: '>=2.0.0' },
      },
      null,
      2
    )
  );

  writeFileSync(join(dir, '.gitignore'), 'node_modules/\ndist/\n');

  console.log(`\nCreated A2A Lite project: ${name}/`);
  console.log(`  ${name}/agent.ts`);
  console.log(`  ${name}/package.json`);
  console.log(`\nNext steps:`);
  console.log(`  cd ${name}`);
  console.log(`  npm install`);
  console.log(`  npm start`);
}

async function cmdInspect(url: string): Promise<void> {
  const cardUrl = url.replace(/\/$/, '') + '/.well-known/agent.json';
  const res = await fetch(cardUrl);
  if (!res.ok) throw new Error(`HTTP ${res.status} from ${cardUrl}`);
  const card = (await res.json()) as Record<string, unknown>;

  const caps = (card.capabilities as Record<string, unknown>) ?? {};
  const capList =
    [caps.streaming ? 'streaming' : null, caps.pushNotifications ? 'push-notifications' : null]
      .filter(Boolean)
      .join(', ') || 'none';

  console.log(`\n+-- ${card.name} v${card.version}`);
  console.log(`|  ${card.description}`);
  console.log(`|  URL: ${card.url}`);
  console.log(`|  Capabilities: ${capList}`);
  console.log(`|`);
  console.log(`|  Skills:`);
  for (const skill of ((card.skills as any[]) ?? [])) {
    const tags = skill.tags?.length ? ` [${skill.tags.join(', ')}]` : '';
    console.log(`|    - ${skill.name}: ${skill.description ?? '-'}${tags}`);
  }
  console.log(`+--`);
}

async function cmdTest(url: string, skill: string, rawParams: string[]): Promise<void> {
  const params: Record<string, unknown> = {};
  for (const p of rawParams) {
    const [k, ...v] = p.split('=');
    const val = v.join('=');
    try {
      params[k] = JSON.parse(val);
    } catch {
      params[k] = val;
    }
  }

  const body = {
    jsonrpc: '2.0',
    method: 'message/send',
    id: Math.random().toString(36).slice(2),
    params: {
      message: {
        role: 'user',
        parts: [{ type: 'text', text: JSON.stringify({ skill, params }) }],
        messageId: Math.random().toString(36).slice(2),
      },
    },
  };

  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  console.log(JSON.stringify(data, null, 2));
}

async function cmdDiscover(urls: string[]): Promise<void> {
  console.log(`\nDiscovering ${urls.length} agent(s)...\n`);
  for (const url of urls) {
    try {
      const cardUrl = url.replace(/\/$/, '') + '/.well-known/agent.json';
      const res = await fetch(cardUrl, { signal: AbortSignal.timeout(5000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const card = (await res.json()) as Record<string, unknown>;
      const skillCount = ((card.skills as unknown[]) ?? []).length;
      const caps = (card.capabilities as Record<string, boolean>) ?? {};
      console.log(
        `OK ${card.name} v${card.version} -- ${skillCount} skills${caps.streaming ? ' [streaming]' : ''}`
      );
      console.log(`  ${url}`);
    } catch (err) {
      console.log(`FAIL ${url} -- ${(err as Error).message}`);
    }
    console.log('');
  }
}

// Main dispatcher
(async () => {
  if (!command || command === '--help' || command === '-h') {
    printHelp();
    process.exit(0);
  }

  if (command === '--version') {
    console.log(getVersion());
    process.exit(0);
  }

  try {
    switch (command) {
      case 'init': {
        const name = args[1];
        if (!name) {
          console.error('Usage: a2a-lite init <name>');
          process.exit(1);
        }
        await cmdInit(name);
        break;
      }
      case 'inspect': {
        const url = args[1];
        if (!url) {
          console.error('Usage: a2a-lite inspect <url>');
          process.exit(1);
        }
        await cmdInspect(url);
        break;
      }
      case 'test': {
        const url = args[1],
          skill = args[2];
        if (!url || !skill) {
          console.error('Usage: a2a-lite test <url> <skill> [--param key=value]');
          process.exit(1);
        }
        const params: string[] = [];
        for (let i = 3; i < args.length; i++) {
          if (args[i] === '--param' || args[i] === '-p') params.push(args[++i]);
        }
        await cmdTest(url, skill, params);
        break;
      }
      case 'discover': {
        const urls = args.slice(1);
        if (!urls.length) {
          console.error('Usage: a2a-lite discover <url...>');
          process.exit(1);
        }
        await cmdDiscover(urls);
        break;
      }
      default:
        console.error(`Unknown command: ${command}`);
        printHelp();
        process.exit(1);
    }
  } catch (err) {
    console.error(`Error: ${(err as Error).message}`);
    process.exit(1);
  }
})();
