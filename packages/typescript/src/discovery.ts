import { z } from 'zod';
import { RemoteAgentError } from './errors.js';

const interfaceSchema = z
  .object({
    url: z.string().url(),
    protocolBinding: z.string(),
    protocolVersion: z.string(),
    tenant: z.string().optional(),
  })
  .passthrough();

const agentCardSchema = z
  .object({
    name: z.string().default('unknown'),
    description: z.string().default(''),
    version: z.string().default('0.0.0'),
    supportedInterfaces: z.array(interfaceSchema).min(1),
    capabilities: z
      .object({
        streaming: z.boolean().optional(),
        pushNotifications: z.boolean().optional(),
      })
      .passthrough()
      .default({}),
    skills: z
      .array(
        z
          .object({
            id: z.string().optional(),
            name: z.string().optional(),
            description: z.string().default(''),
          })
          .passthrough(),
      )
      .default([]),
  })
  .passthrough();

export type DiscoveryCard = z.infer<typeof agentCardSchema>;

/** Validate external discovery data before it can select a request destination. */
export function parseDiscoveryCard(value: unknown): DiscoveryCard {
  const legacy = z.object({ url: z.unknown().optional(), protocolVersion: z.unknown().optional() }).passthrough();
  const oldCard = legacy.safeParse(value);
  if (
    oldCard.success &&
    !('supportedInterfaces' in oldCard.data) &&
    ('url' in oldCard.data || 'protocolVersion' in oldCard.data)
  ) {
    throw new RemoteAgentError('Agent speaks A2A 0.3, not supported by a2a-lite 1.0');
  }
  const result = agentCardSchema.safeParse(value);
  if (!result.success) {
    throw new RemoteAgentError('Invalid A2A Agent Card: expected valid supportedInterfaces, capabilities and skills.');
  }
  return result.data;
}

/** Prefer card order among compatible JSON-RPC interfaces for the requested tenant. */
export function selectJsonRpcInterface(card: Pick<DiscoveryCard, 'supportedInterfaces'>, tenant?: string) {
  const compatible = card.supportedInterfaces.filter((entry) => {
    if (entry.protocolBinding !== 'JSONRPC' || !/^1\.0(?:\.\d+)?$/.test(entry.protocolVersion)) return false;
    const url = new URL(entry.url);
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password && !url.hash;
  });
  const candidate = tenant
    ? (compatible.find((entry) => entry.tenant === tenant) ?? compatible.find((entry) => !entry.tenant))
    : compatible[0];
  if (!candidate)
    throw new RemoteAgentError(
      'Agent does not advertise a compatible JSONRPC interface for the requested tenant and A2A 1.0.',
    );
  return candidate;
}
