import { RemoteAgentError } from './errors.js';

export type CredentialProvider = (request: {
  url: string;
  signal?: AbortSignal;
}) => Record<string, string> | Promise<Record<string, string>>;

export interface RemoteCallOptions {
  headers?: Record<string, string>;
  credentialProvider?: CredentialProvider;
  tenant?: string;
  /** Continue a real task after its previous execution lease ended. */
  taskId?: string;
  returnImmediately?: boolean;
  /** Explicit credential boundary. Discovery never expands this boundary. */
  credentialOrigin?: string;
  allowedCredentialOrigins?: readonly string[];
}

export function bindRemoteOptions(options: RemoteCallOptions = {}, agentUrl: string): RemoteCallOptions {
  return { ...options, credentialOrigin: new URL(options.credentialOrigin ?? agentUrl).origin };
}

/** Resolve rotating credentials for every operation, without following redirects. */
export async function remoteFetch(url: string, options: RemoteCallOptions, init: RequestInit): Promise<Response> {
  const target = new URL(url);
  if (!['http:', 'https:'].includes(target.protocol) || target.username || target.password) {
    throw new RemoteAgentError('Agent URL must use HTTP(S) without embedded credentials.');
  }
  if (
    (options.headers || options.credentialProvider) &&
    options.credentialOrigin &&
    target.origin !== new URL(options.credentialOrigin).origin &&
    !options.allowedCredentialOrigins?.some((origin) => new URL(origin).origin === target.origin)
  ) {
    throw new RemoteAgentError('Agent interface is outside the configured credential origin.');
  }
  const signal = init.signal;
  signal?.throwIfAborted();
  const pending = Promise.resolve(options.credentialProvider?.({ url, signal: signal ?? undefined }));
  let abort: (() => void) | undefined;
  const interrupted = new Promise<never>((_resolve, reject) => {
    if (signal) {
      abort = () => reject(signal.reason);
      signal.addEventListener('abort', abort, { once: true });
    }
  });
  let provided: Record<string, string> | undefined;
  try {
    provided = await Promise.race([pending, interrupted]);
  } finally {
    if (abort) signal?.removeEventListener('abort', abort);
  }
  const headers = new Headers({ ...options.headers, ...provided });
  new Headers(init.headers).forEach((value, key) => headers.set(key, value));
  return fetch(url, { ...init, headers: Object.fromEntries(headers), redirect: 'error' });
}
