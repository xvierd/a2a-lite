/**
 * Client-side SSE streaming consumption.
 *
 * Demonstrates how one agent can consume a streaming response from another
 * agent over HTTP using `delegate()` with `{ stream: true }`.
 *
 * Usage:
 *   # Terminal 1 — start the story agent
 *   npx tsx examples/18_client_streaming.ts story
 *
 *   # Terminal 2 — start the display agent
 *   npx tsx examples/18_client_streaming.ts display
 *
 * Then call the display agent:
 *   curl -X POST http://localhost:8788 \
 *     -H "Content-Type: application/json" \
 *     -d '{"jsonrpc":"2.0","method":"message/send","id":"1","params":{"message":{"role":"user","parts":[{"kind":"text","text":"{\"skill\":\"displayStory\",\"params\":{\"topic\":\"a brave robot\"}}"}],"messageId":"m1"}}}'
 */
import { Agent, AgentNetwork } from '../src';

// --- Story Agent (port 8787) — streaming skill ---

function createStoryAgent(): Agent {
  const agent = new Agent({
    name: 'StoryAgent',
    description: 'Tells stories word by word using streaming',
  });

  agent.skill(
    'tellStory',
    { description: 'Tell a short story about a topic', streaming: true },
    async function* ({ topic }: { topic: string }) {
      const story = `Once upon a time, there was ${topic}. ` +
        `They went on an amazing adventure. ` +
        `Along the way, they learned the value of friendship. ` +
        `And they all lived happily ever after. The end.`;

      const words = story.split(' ');
      for (const word of words) {
        yield word + ' ';
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
    },
  );

  return agent;
}

// --- Display Agent (port 8788) — consumes the stream ---

function createDisplayAgent(): Agent {
  const network = new AgentNetwork();
  network.add('story', 'http://localhost:8787');

  const agent = new Agent({
    name: 'DisplayAgent',
    description: 'Displays a story streamed from StoryAgent',
    network,
  });

  agent.skill('displayStory', async ({ topic }: { topic: string }) => {
    const gen = await agent.delegate('story', 'tellStory', { topic }, { stream: true });

    let fullStory = '';
    for await (const chunk of gen as AsyncGenerator<string>) {
      process.stdout.write(chunk);
      fullStory += chunk;
    }
    process.stdout.write('\n');

    return { topic, story: fullStory.trim() };
  });

  return agent;
}

// --- Main ---

const role = process.argv[2] ?? 'story';

switch (role) {
  case 'story': {
    const agent = createStoryAgent();
    agent.run({ port: 8787 });
    break;
  }
  case 'display': {
    const agent = createDisplayAgent();
    agent.run({ port: 8788 });
    break;
  }
  default:
    console.error(`Unknown role: ${role}. Use "story" or "display".`);
    process.exit(1);
}
