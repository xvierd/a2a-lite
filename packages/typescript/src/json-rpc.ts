import { v4 as uuidv4 } from 'uuid';
import { RemoteAgentError } from './errors.js';
import { bindRemoteOptions, remoteFetch, type RemoteCallOptions } from './remote-auth.js';

type RpcResult = { jsonrpc: '2.0'; id: string; result: unknown };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function validateResponse(value: unknown, id: string): RpcResult {
  if (!isRecord(value) || value.jsonrpc !== '2.0') throw new RemoteAgentError('Invalid JSON-RPC response version.');
  if (value.id !== id) throw new RemoteAgentError('JSON-RPC response ID mismatch.', value);
  if (Object.hasOwn(value, 'result') === Object.hasOwn(value, 'error')) {
    throw new RemoteAgentError('JSON-RPC response must contain exactly one of result or error.', value);
  }
  if ('error' in value) {
    const error = value.error;
    if (!isRecord(error) || !Number.isInteger(error.code) || typeof error.message !== 'string') {
      throw new RemoteAgentError('Invalid JSON-RPC error object.', value);
    }
    throw new RemoteAgentError(error.message, value);
  }
  return value as RpcResult;
}

async function postRpc(
  url: string,
  method: string,
  params: Record<string, unknown>,
  options: RemoteCallOptions,
  signal: AbortSignal,
  accept: string,
) {
  const id = uuidv4().replace(/-/g, '');
  const response = await remoteFetch(url, bindRemoteOptions(options, url), {
    method: 'POST',
    headers: { 'A2A-Version': '1.0', 'Content-Type': 'application/json', Accept: accept },
    body: JSON.stringify({ jsonrpc: '2.0', id, method, params: { ...params, tenant: options.tenant } }),
    signal,
  });
  return { id, response };
}

async function readResponse(response: Response, id: string): Promise<RpcResult> {
  let value: unknown;
  try {
    value = await response.json();
  } catch (error) {
    if (!(error instanceof SyntaxError)) throw error;
    if (response.ok) throw new RemoteAgentError('Invalid JSON in JSON-RPC response.');
  }
  if (!response.ok && !(isRecord(value) && 'jsonrpc' in value && 'error' in value)) {
    throw new RemoteAgentError(`Remote agent returned HTTP ${response.status}`, { status: response.status });
  }
  return validateResponse(value, id);
}

export async function requestJsonRpc(
  url: string,
  method: string,
  params: Record<string, unknown>,
  timeout: number,
  options: RemoteCallOptions,
): Promise<RpcResult> {
  const { response, id } = await postRpc(
    url,
    method,
    params,
    options,
    AbortSignal.timeout(timeout),
    'application/json',
  );
  return readResponse(response, id);
}

/** SDK 1.3.0 only splits on LF and dispatches unfinished data at EOF. */
async function* sseData(body: NonNullable<Response['body']>): AsyncGenerator<string> {
  const decoder = new TextDecoder();
  const reader = body.getReader();
  let line = '';
  let data: string[] = [];
  let skipLeadingLF = false;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      let chunk = decoder.decode(value, { stream: true });
      if (!chunk) continue;
      if (skipLeadingLF && chunk.startsWith('\n')) chunk = chunk.slice(1);
      skipLeadingLF = chunk.endsWith('\r');
      let start = 0;
      for (const end of chunk.matchAll(/\r\n|\r|\n/g)) {
        line += chunk.slice(start, end.index);
        start = end.index + end[0].length;
        if (line === '' && data.length) {
          yield data.join('\n');
          data = [];
        } else if (line === 'data' || line.startsWith('data:')) {
          data.push(line.slice(5).replace(/^ /, ''));
        }
        line = '';
      }
      line += chunk.slice(start);
    }
    line += decoder.decode();
    if (line || data.length) throw new RemoteAgentError('SSE stream closed before the end of an event.');
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export async function* streamJsonRpc(
  url: string,
  method: string,
  params: Record<string, unknown>,
  timeout: number,
  options: RemoteCallOptions,
): AsyncGenerator<Record<string, unknown>> {
  const { response, id } = await postRpc(
    url,
    method,
    params,
    options,
    AbortSignal.timeout(timeout),
    'text/event-stream',
  );
  const mime = response.headers.get('content-type')?.split(';')[0].trim().toLowerCase();
  if (!response.ok || mime !== 'text/event-stream') {
    if (!response.ok || mime === 'application/json' || mime?.endsWith('+json')) {
      await readResponse(response, id);
    } else {
      await response.body?.cancel();
    }
    throw new RemoteAgentError('Expected a text/event-stream response.');
  }
  if (!response.body) throw new RemoteAgentError('Empty SSE response body.');
  for await (const data of sseData(response.body)) {
    let value: unknown;
    try {
      value = JSON.parse(data);
    } catch {
      throw new RemoteAgentError('Invalid JSON in SSE event.');
    }
    const { result } = validateResponse(value, id);
    if (!isRecord(result)) throw new RemoteAgentError('Invalid A2A stream result.');
    yield result;
  }
}
