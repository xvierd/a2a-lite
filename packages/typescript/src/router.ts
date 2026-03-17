/**
 * Router for path-based multi-agent routing.
 *
 * Mounts multiple A2A agents under a single Express server at different URL prefixes.
 * Each sub-agent retains its own executor, middleware, auth, and task store.
 *
 * Example:
 *   import { Router } from 'a2a-lite';
 *
 *   const weather = new Agent({ name: "WeatherAgent", description: "Weather forecasts" });
 *   const hotels = new Agent({ name: "HotelAgent", description: "Hotel search" });
 *
 *   weather.skill("forecast", async ({ city }) => `Sunny in ${city}`);
 *   hotels.skill("search", async ({ city }) => [{ name: "Grand Hotel", city }]);
 *
 *   const router = new Router();
 *   router.mount("/weather", weather);
 *   router.mount("/hotels", hotels);
 *   router.run();
 *
 * The merged agent card is at /.well-known/agent.json.
 */

import express, { Express } from 'express';
import type { Agent } from './agent.js';

export class Router {
  private mounts: Array<[string, Agent]> = [];

  /**
   * Mount an agent at a URL prefix.
   *
   * @param prefix - URL prefix (e.g., "/weather"). Leading slash is added if missing.
   * @param agent - The Agent instance to mount.
   */
  mount(prefix: string, agent: Agent): this {
    if (!prefix.startsWith('/')) prefix = '/' + prefix;
    prefix = prefix.replace(/\/$/, '');
    this.mounts.push([prefix, agent]);
    return this;
  }

  /**
   * Build the merged agent card combining skills from all mounted agents.
   */
  buildMergedCard(host = 'localhost', port = 8787): Record<string, unknown> {
    const allSkills: Array<Record<string, unknown>> = [];
    const names: string[] = [];
    const descriptions: string[] = [];
    let hasStreaming = false;

    for (const [prefix, agent] of this.mounts) {
      names.push(agent.name);
      descriptions.push(agent.description);
      const card = agent.buildAgentCard(host, port);
      if (card.capabilities?.streaming) hasStreaming = true;
      for (const skill of card.skills ?? []) {
        allSkills.push({
          id: `${prefix.replace(/^\//, '')}/${skill.id}`,
          name: skill.name,
          description: `[${agent.name}] ${skill.description ?? ''}`,
          tags: skill.tags ?? [],
        });
      }
    }

    return {
      name: names.join(' + ') || 'Router',
      description: descriptions.join('; ') || 'Multi-agent router',
      version: '1.0.0',
      url: `http://${host}:${port}`,
      protocolVersion: '0.3.0',
      capabilities: { streaming: hasStreaming, pushNotifications: false },
      defaultInputModes: ['text'],
      defaultOutputModes: ['text'],
      skills: allSkills,
    };
  }

  /**
   * Build an Express app with all agents mounted at their prefixes.
   */
  buildApp(host = 'localhost', port = 8787): Express {
    const app = express();
    const mergedCard = this.buildMergedCard(host, port);

    // Merged agent card at root
    app.get('/.well-known/agent.json', (_req, res) => {
      res.json(mergedCard);
    });

    // Mount each agent's Express app at its prefix
    for (const [prefix, agent] of this.mounts) {
      app.use(prefix, agent.buildApp());
    }

    return app;
  }

  /**
   * Start the router server.
   */
  async run(options: { host?: string; port?: number; logLevel?: string } = {}): Promise<void> {
    const { host = '0.0.0.0', port = 8787 } = options;
    const displayHost = host === '0.0.0.0' ? 'localhost' : host;
    const app = this.buildApp(displayHost, port);

    console.log(`\nA2A Lite Router → http://${displayHost}:${port}`);
    for (const [prefix, agent] of this.mounts) {
      const skillCount = agent.buildAgentCard().skills?.length ?? 0;
      console.log(`  ${prefix} → ${agent.name} (${skillCount} skills)`);
    }

    await new Promise<void>((resolve) => {
      app.listen(port, host, () => resolve());
    });
  }
}
