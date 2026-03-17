/**
 * Multi-agent network with orchestration.
 *
 * Demonstrates how to build a network of specialized agents that an
 * orchestrator can delegate tasks to using `AgentNetwork` and `agent.delegate()`.
 *
 * Usage:
 *   # Terminal 1 — start the weather agent
 *   npx ts-node examples/17_multi_agent_network.ts weather
 *
 *   # Terminal 2 — start the hotel agent
 *   npx ts-node examples/17_multi_agent_network.ts hotels
 *
 *   # Terminal 3 — start the orchestrator (default)
 *   npx ts-node examples/17_multi_agent_network.ts
 *
 * Then call the orchestrator:
 *   curl -X POST http://localhost:8787 \
 *     -H "Content-Type: application/json" \
 *     -d '{"jsonrpc":"2.0","method":"message/send","id":"1","params":{"message":{"role":"user","parts":[{"kind":"text","text":"{\"skill\":\"plan_trip\",\"params\":{\"city\":\"Tokyo\"}}"}],"messageId":"m1"}}}'
 */
import { Agent, AgentNetwork } from '../src';

// --- Weather Agent (port 8788) ---

function createWeatherAgent(): Agent {
  const agent = new Agent({
    name: 'WeatherAgent',
    description: 'Provides weather forecasts for cities',
  });

  agent.skill('forecast', async ({ city }: { city: string }) => {
    // Simulated weather data
    const forecasts: Record<string, object> = {
      tokyo: { temp: 22, condition: 'Partly Cloudy', humidity: 65 },
      paris: { temp: 18, condition: 'Rainy', humidity: 80 },
      nyc: { temp: 15, condition: 'Sunny', humidity: 45 },
    };
    const key = city.toLowerCase();
    return forecasts[key] ?? { temp: 20, condition: 'Unknown', humidity: 50 };
  });

  agent.skill('alerts', async ({ city }: { city: string }) => {
    // Simulated weather alerts
    const alerts: Record<string, string[]> = {
      tokyo: ['Typhoon warning in effect'],
      paris: ['Heavy rain expected tomorrow'],
    };
    return alerts[city.toLowerCase()] ?? [];
  });

  return agent;
}

// --- Hotel Agent (port 8789) ---

function createHotelAgent(): Agent {
  const agent = new Agent({
    name: 'HotelAgent',
    description: 'Searches for hotel availability and pricing',
  });

  agent.skill('search', async ({ city, checkin, checkout }: { city: string; checkin?: string; checkout?: string }) => {
    // Simulated hotel data
    const hotels: Record<string, object[]> = {
      tokyo: [
        { name: 'Tokyo Grand Hotel', price: 250, rating: 4.5 },
        { name: 'Shinjuku Inn', price: 120, rating: 4.0 },
      ],
      paris: [
        { name: 'Hotel de Paris', price: 300, rating: 4.7 },
        { name: 'Le Petit Hostel', price: 80, rating: 3.8 },
      ],
      nyc: [
        { name: 'Manhattan Suites', price: 350, rating: 4.3 },
        { name: 'Brooklyn B&B', price: 150, rating: 4.1 },
      ],
    };
    const key = city.toLowerCase();
    return {
      city,
      checkin: checkin ?? 'flexible',
      checkout: checkout ?? 'flexible',
      hotels: hotels[key] ?? [],
    };
  });

  return agent;
}

// --- Orchestrator Agent (port 8787) ---

function createOrchestratorAgent(): Agent {
  const network = new AgentNetwork();
  network.add('weather', 'http://localhost:8788');
  network.add('hotels', 'http://localhost:8789');

  const orchestrator = new Agent({
    name: 'TravelPlanner',
    description: 'Plans trips by coordinating weather and hotel agents',
    network,
  });

  // Plan a full trip by delegating to sub-agents
  orchestrator.skill('plan_trip', async ({ city }: { city: string }) => {
    const [weather, hotels] = await Promise.all([
      orchestrator.delegate('weather', 'forecast', { city }),
      orchestrator.delegate('hotels', 'search', { city }),
    ]);
    return { city, weather, hotels };
  });

  // Check weather alerts across all known cities
  orchestrator.skill('check_alerts', async ({ city }: { city: string }) => {
    const alerts = await orchestrator.delegate('weather', 'alerts', { city });
    return { city, alerts };
  });

  // List all agents in the network
  orchestrator.skill('list_agents', async () => {
    return network.list();
  });

  // Broadcast a request to all agents (using network.call directly)
  orchestrator.skill('network_status', async () => {
    const agents = network.list();
    const status: Record<string, string> = {};
    for (const name of Object.keys(agents)) {
      try {
        await network.call(name, 'forecast', { city: 'test' });
        status[name] = 'online';
      } catch {
        status[name] = 'offline';
      }
    }
    return status;
  });

  return orchestrator;
}

// --- Main: select agent based on CLI argument ---

const role = process.argv[2] ?? 'orchestrator';

switch (role) {
  case 'weather': {
    const agent = createWeatherAgent();
    agent.run({ port: 8788 });
    break;
  }
  case 'hotels': {
    const agent = createHotelAgent();
    agent.run({ port: 8789 });
    break;
  }
  default: {
    const agent = createOrchestratorAgent();
    agent.run({ port: 8787 });
    break;
  }
}
