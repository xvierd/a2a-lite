/**
 * Using middleware for logging, timing, auth, etc.
 *
 * Run: npx ts-node examples/07_middleware.ts
 */
import { Agent } from '../src';

const agent = new Agent({ name: 'MiddlewareDemo', description: 'Shows middleware' });

agent.use(async (ctx, next) => {
  console.log('Request: skill=' + ctx.skill + ', params=' + JSON.stringify(ctx.params));
  const start = Date.now();
  const result = await next();
  console.log('Response: ' + (Date.now() - start) + 'ms');
  return result;
});

agent.use(async (ctx, next) => {
  ctx.metadata['request_id'] = 'req-' + Date.now();
  return next();
});

agent.skill('slow_operation', { description: 'Slow operation' }, async ({ seconds = 1 }: { seconds?: number }) => {
  await new Promise(resolve => setTimeout(resolve, seconds * 1000));
  return { waited: seconds, message: 'Done!' };
});

agent.skill('fast_operation', { description: 'Quick calculation' }, async ({ x }: { x: number }) => ({ result: x * 2 }));

agent.run({ port: 8787 });
