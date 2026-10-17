import { lookup } from 'node:dns/promises';
import { request as httpRequest } from 'node:http';
import { request as httpsRequest, type RequestOptions } from 'node:https';
import type { LookupAddress } from 'node:dns';
import ipaddr from 'ipaddr.js';
import { z } from 'zod';

const webhookUrlSchema = z.string().max(2048).url();

export function parseWebhookUrl(value: string): URL {
  const parsed = webhookUrlSchema.safeParse(value);
  if (!parsed.success) throw new Error('Webhook URL must be an absolute HTTP(S) URL.');
  const url = new URL(parsed.data);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.hash) {
    throw new Error('Webhook URL must use HTTP(S) without credentials or a fragment.');
  }
  return url;
}

export function isPublicAddress(address: string): boolean {
  try {
    const parsed = ipaddr.process(address);
    if (parsed.range() !== 'unicast') return false;
    return parsed.kind() === 'ipv4' || (parsed as ipaddr.IPv6).match(ipaddr.IPv6.parse('2000::'), 3);
  } catch {
    return false;
  }
}

async function abortable<T>(pending: Promise<T>, signal: AbortSignal): Promise<T> {
  signal.throwIfAborted();
  let onAbort: () => void;
  const interrupted = new Promise<never>((_resolve, reject) => {
    onAbort = () => reject(new Error('Webhook request timed out.'));
    signal.addEventListener('abort', onAbort, { once: true });
  });
  try {
    return await Promise.race([pending, interrupted]);
  } finally {
    signal.removeEventListener('abort', onAbort!);
  }
}

/** Resolve and validate every address; mixed public/private answers fail closed. */
export async function resolveWebhookTarget(
  value: string,
  signal: AbortSignal,
): Promise<{
  url: URL;
  address: LookupAddress;
}> {
  const url = parseWebhookUrl(value);
  const hostname = url.hostname.replace(/^\[|\]$/g, '');
  const addresses = ipaddr.isValid(hostname)
    ? [{ address: hostname, family: ipaddr.parse(hostname).kind() === 'ipv4' ? 4 : 6 }]
    : await abortable(lookup(hostname, { all: true, verbatim: true }), signal);
  signal.throwIfAborted();
  if (!addresses.length || addresses.some(({ address }) => !isPublicAddress(address))) {
    throw new Error('Webhook URL must resolve only to public unicast addresses.');
  }
  return { url, address: addresses[0] };
}

export interface WebhookRequest {
  body: string;
  headers: Record<string, string>;
  timeoutMs: number;
}

/** Pin the validated DNS address while retaining the URL's HTTP Host and TLS identity. */
export async function postWebhook(destination: string, options: WebhookRequest): Promise<void> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs);
  try {
    const { url, address } = await resolveWebhookTarget(destination, controller.signal);
    const send = url.protocol === 'https:' ? httpsRequest : httpRequest;
    await new Promise<void>((resolve, reject) => {
      const requestOptions: RequestOptions = {
        method: 'POST',
        headers: { ...options.headers, Host: url.host },
        signal: controller.signal,
        agent: false,
        family: address.family,
        servername: url.hostname.replace(/^\[|\]$/g, ''),
        lookup: (_hostname, lookupOptions, callback) => {
          if (lookupOptions.all) callback(null, [address]);
          else callback(null, address.address, address.family);
        },
      };
      const req = send(url, requestOptions, (response) => {
        // Node's HTTP client never follows redirects; do not consume unbounded callback bodies.
        response.destroy();
        const status = response.statusCode ?? 0;
        if (status >= 200 && status < 300) resolve();
        else reject(new Error(`Webhook responded with HTTP ${status}.`));
      });
      req.on('error', () => reject(new Error('Webhook delivery failed.')));
      req.end(options.body);
    });
  } finally {
    clearTimeout(timer);
  }
}
