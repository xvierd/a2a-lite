/**
 * Task Handle & Agent Card Discovery
 *
 * Demonstrates two features:
 *   1. Agent card discovery — inspect a remote agent's skills before calling it
 *   2. TaskHandle — get a handle to a remote task with its ID for later reference
 *
 * Architecture:
 *   - DataAgent (port 8787): exposes "lookup" and "stats" skills
 *   - OrchestratorAgent (port 8788): discovers DataAgent, delegates with handles
 *
 * Usage:
 *   # Terminal 1 — start the data agent
 *   npx tsx examples/06_task_handle_discovery.ts data
 *
 *   # Terminal 2 — start the orchestrator
 *   npx tsx examples/06_task_handle_discovery.ts
 *
 * Then call the orchestrator:
 *   curl -X POST http://localhost:8788 \
 *     -H "Content-Type: application/json" \
 *     -d '{"jsonrpc":"2.0","method":"message/send","id":"1","params":{"message":{"role":"user","parts":[{"kind":"text","text":"{\"skill\":\"query\",\"params\":{\"key\":\"users\"}}"}],"messageId":"m1"}}}'
 */
import {
  Agent,
  AgentNetwork,
  TaskHandle,
  discoverAgent,
} from '../src';

// ---------------------------------------------------------------------------
// DataAgent (port 8787) — a simple data-serving agent
// ---------------------------------------------------------------------------

function createDataAgent(): Agent {
  const agent = new Agent({
    name: 'DataAgent',
    description: 'Serves data lookups and statistics',
  });

  agent.skill('lookup', async ({ key }: { key: string }) => {
    const data: Record<string, unknown> = {
      users: [{ id: 1, name: 'Alice' }, { id: 2, name: 'Bob' }],
      products: [{ id: 1, name: 'Widget', price: 9.99 }],
    };
    return data[key] ?? [];
  });

  agent.skill('stats', async () => {
    return { uptime: '4h 32m', requests: 1042, errors: 3 };
  });

  return agent;
}

// ---------------------------------------------------------------------------
// OrchestratorAgent (port 8788) — discovers DataAgent, delegates with handles
// ---------------------------------------------------------------------------

function createOrchestratorAgent(): Agent {
  const network = new AgentNetwork();
  network.add('data', 'http://localhost:8787');

  const orchestrator = new Agent({
    name: 'OrchestratorAgent',
    description: 'Queries data agent with discovery and task handles',
    network,
  });

  // "query" skill: discovers the data agent, validates the skill, delegates
  orchestrator.skill('query', async ({ key }: { key: string }) => {
    // Step 1: Discover the DataAgent's capabilities
    const card = await discoverAgent('http://localhost:8787');
    console.log(`Discovered agent: ${card.name} v${card.version}`);
    console.log(`  Skills: ${card.skills.map((s) => s.id).join(', ')}`);
    console.log(`  Streaming: ${card.supportsStreaming}`);

    // Step 2: Delegate with returnHandle to get a TaskHandle back
    const handle = await orchestrator.delegate('data', 'lookup', { key }, {
      discover: true,
      returnHandle: true,
    }) as TaskHandle;

    console.log(`Task ID: ${handle.taskId}`);
    console.log(`Result: ${handle.toString()}`);

    // Step 3: Check task status via the handle's convenience method
    try {
      const status = await handle.getStatus();
      console.log('Status (via handle):', JSON.stringify(status, null, 2));
    } catch (err) {
      console.log('tasks/get not supported by this agent (expected for simple agents)');
    }

    // Step 4: Or check via the network by agent name
    try {
      const status2 = await network.getTask('data', handle.taskId);
      console.log('Status (via network):', JSON.stringify(status2, null, 2));
    } catch (err) {
      console.log('tasks/get via network not supported (expected for simple agents)');
    }

    // Cancel if needed:
    // await handle.cancel();
    // await network.cancelTask('data', handle.taskId);

    return {
      taskId: handle.taskId,
      data: handle.result,
      agent: card.name,
    };
  });

  return orchestrator;
}

// ---------------------------------------------------------------------------
// Main: select agent based on CLI argument
// ---------------------------------------------------------------------------

const role = process.argv[2] ?? 'orchestrator';

switch (role) {
  case 'data': {
    const agent = createDataAgent();
    agent.run({ port: 8787 });
    break;
  }
  default: {
    const agent = createOrchestratorAgent();
    agent.run({ port: 8788 });
    break;
  }
}
