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
import { createRequire } from 'node:module';
import { join, resolve } from 'node:path';

const args = process.argv.slice(2);
const command = args[0];

function printHelp(): void {
  console.log(`
A2A Lite CLI v${getVersion()}

Commands:
  init <name>                 Create a new A2A Lite agent project
  inspect <url>               Inspect an agent's capabilities
  info <url>                  Show agent info in a compact format
  test <url> <skill> [opts]   Call a skill and show the result
  discover <url...>           Discover and compare multiple agents
  doctor [url]                Diagnose the environment (and a remote agent)

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
    return '1.0.0';
  }
}

/** Installed version of @a2a-js/sdk, or null if it cannot be resolved. */
function getSdkVersion(): string | null {
  try {
    // The SDK's exports map does not expose ./package.json, so resolve the
    // entry point (…/@a2a-js/sdk/dist/index.js) and read two levels up.
    const require = createRequire(import.meta.url);
    const entry = require.resolve('@a2a-js/sdk');
    const pkg = JSON.parse(readFileSync(join(entry, '..', '..', 'package.json'), 'utf8'));
    return pkg.version ?? null;
  } catch {
    return null;
  }
}

const V03_MESSAGE =
  'This agent speaks A2A 0.3 — a2a-lite 1.0 requires protocol v1.0. ' +
  'Upgrade the agent to A2A v1.0 (see https://a2a-protocol.org/latest/).';

function isV03Error(err: unknown): boolean {
  return err instanceof Error && err.message.includes('speaks A2A 0.3');
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
        dependencies: { 'a2a-lite': '>=1.0.0', express: '>=4.0.0' },
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

/** Fetch the A2A v1.0 agent card, rejecting 0.3 agents with a clear error. */
async function fetchAgentCard(url: string, timeoutMs?: number): Promise<Record<string, unknown>> {
  const cardUrl = url.replace(/\/$/, '') + '/.well-known/agent-card.json';
  const res = await fetch(cardUrl, timeoutMs ? { signal: AbortSignal.timeout(timeoutMs) } : undefined);
  if (!res.ok) throw new Error(`HTTP ${res.status} from ${cardUrl}`);
  const card = (await res.json()) as Record<string, unknown>;

  // Detect A2A 0.3 cards (root `url` + `protocolVersion`, no supportedInterfaces)
  if (!('supportedInterfaces' in card) && ('url' in card || 'protocolVersion' in card)) {
    throw new Error(V03_MESSAGE);
  }
  return card;
}

/** Primary interface URL advertised by a v1.0 agent card. */
function cardInterfaceUrl(card: Record<string, unknown>, fallback: string): string {
  const interfaces = (card.supportedInterfaces as Array<Record<string, unknown>>) ?? [];
  return interfaces.length > 0 ? (interfaces[0].url as string) : fallback;
}

async function cmdInspect(url: string): Promise<void> {
  const card = await fetchAgentCard(url);

  const caps = (card.capabilities as Record<string, unknown>) ?? {};
  const capList =
    [caps.streaming ? 'streaming' : null, caps.pushNotifications ? 'push-notifications' : null]
      .filter(Boolean)
      .join(', ') || 'none';

  console.log(`\n+-- ${card.name} v${card.version}`);
  console.log(`|  ${card.description}`);
  console.log(`|  URL: ${cardInterfaceUrl(card, url)}`);
  console.log(`|  Capabilities: ${capList}`);
  console.log(`|`);
  console.log(`|  Skills:`);
  for (const skill of ((card.skills as any[]) ?? [])) {
    const tags = skill.tags?.length ? ` [${skill.tags.join(', ')}]` : '';
    console.log(`|    - ${skill.name}: ${skill.description ?? '-'}${tags}`);
  }
  console.log(`+--`);
}

async function cmdInfo(url: string): Promise<void> {
  const card = await fetchAgentCard(url);

  const agentName = (card.name as string) ?? 'Unknown';
  const agentVersion = (card.version as string) ?? '?';
  const agentDesc = (card.description as string) ?? '-';
  const agentUrl = cardInterfaceUrl(card, url);

  console.log(`Agent: ${agentName} (v${agentVersion})`);
  console.log(`Description: ${agentDesc}`);
  console.log(`URL: ${agentUrl}`);

  const skills = (card.skills as any[]) ?? [];
  if (skills.length) {
    console.log('');
    console.log('Skills:');
    for (const skill of skills) {
      const skillName = skill.name ?? skill.id ?? '?';
      const skillDesc = skill.description ?? '-';
      console.log(`  ${skillName}`);
      console.log(`    Description: ${skillDesc}`);

      const inputSchema = skill.inputSchema ?? {};
      const properties = inputSchema.properties ?? {};
      const requiredParams: string[] = inputSchema.required ?? [];

      const paramNames = Object.keys(properties);
      if (paramNames.length) {
        console.log('    Parameters:');
        for (const paramName of paramNames) {
          const paramType = properties[paramName].type ?? 'any';
          const reqLabel = requiredParams.includes(paramName) ? 'required' : 'optional';
          console.log(`      ${paramName} (${paramType}, ${reqLabel})`);
        }
      }
    }
  }
}

async function cmdTest(url: string, skill: string, rawParams: string[]): Promise<void> {
  // Detect legacy 0.3 agents before sending (fall through if the card cannot
  // be fetched; the SendMessage error will surface instead)
  try {
    await fetchAgentCard(url);
  } catch (err) {
    if (isV03Error(err)) throw err;
  }

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
    method: 'SendMessage',
    id: Math.random().toString(36).slice(2),
    params: {
      message: {
        role: 'ROLE_USER',
        parts: [{ text: JSON.stringify({ skill, params }) }],
        messageId: Math.random().toString(36).slice(2),
      },
    },
  };

  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'A2A-Version': '1.0' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  console.log(JSON.stringify(data, null, 2));
}

async function cmdDoctor(url?: string): Promise<void> {
  let healthy = true;

  const sdkVersion = getSdkVersion();
  const nodeVersion = process.versions.node;
  const nodeMajor = parseInt(nodeVersion.split('.')[0], 10);

  console.log('\nA2A Lite doctor\n');
  console.log('Versions:');
  console.log(`  a2a-lite:    ${getVersion()}`);
  console.log(`  @a2a-js/sdk: ${sdkVersion ?? 'not found'}`);
  console.log(`  Node.js:     v${nodeVersion}`);
  console.log('');

  if (!sdkVersion) {
    healthy = false;
    console.log('ERROR @a2a-js/sdk is not installed.');
    console.log('  Install it with: npm install "@a2a-js/sdk@^1.0.1"');
  } else if (!sdkVersion.startsWith('1.')) {
    healthy = false;
    console.log(`WARN @a2a-js/sdk ${sdkVersion} is outside the supported range >=1.0.1 <2.0.`);
    console.log('  a2a-lite 1.0 targets A2A protocol v1.0. Please upgrade:');
    console.log('  npm install "@a2a-js/sdk@^1.0.1"');
  } else {
    console.log(`OK @a2a-js/sdk ${sdkVersion} is within the supported range (>=1.0.1 <2.0)`);
  }

  if (nodeMajor < 20) {
    console.log(`WARN Node.js >= 20 is required (found v${nodeVersion}).`);
  } else {
    console.log(`OK Node.js v${nodeVersion} (>= 20)`);
  }

  if (url) {
    console.log('');
    try {
      const card = await fetchAgentCard(url);
      console.log(`Remote agent: ${url}`);
      console.log(`  ${card.name} v${card.version} -- ${card.description ?? '-'}`);
      const interfaces = (card.supportedInterfaces as Array<Record<string, unknown>>) ?? [];
      console.log('  Interfaces:');
      for (const iface of interfaces) {
        console.log(`    - ${iface.url} (${iface.protocolBinding}, protocol ${iface.protocolVersion})`);
      }
      const caps = (card.capabilities as Record<string, unknown>) ?? {};
      const capList =
        [
          caps.streaming ? 'streaming' : null,
          caps.pushNotifications ? 'push-notifications' : null,
          Array.isArray(caps.extensions) && caps.extensions.length
            ? `${caps.extensions.length} extension(s)`
            : null,
        ]
          .filter(Boolean)
          .join(', ') || 'none';
      console.log(`  Capabilities: ${capList}`);
      const signatures = (card.signatures as unknown[]) ?? [];
      if (signatures.length) console.log(`  Signatures: ${signatures.length} (card is signed)`);
    } catch (err) {
      healthy = false;
      console.log(`ERROR ${(err as Error).message}`);
    }
  }

  if (!healthy) process.exit(1);
}

async function cmdDiscover(urls: string[]): Promise<void> {
  console.log(`\nDiscovering ${urls.length} agent(s)...\n`);
  for (const url of urls) {
    try {
      const card = await fetchAgentCard(url, 5000);
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
      case 'info': {
        const url = args[1];
        if (!url) {
          console.error('Usage: a2a-lite info <url>');
          process.exit(1);
        }
        await cmdInfo(url);
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
      case 'doctor': {
        await cmdDoctor(args[1]);
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
