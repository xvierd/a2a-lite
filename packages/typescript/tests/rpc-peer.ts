/** JSON-RPC peer fixture. Every request gets its own correlated response. */
export function rpcReply(payload: Record<string, unknown>, status = 200): typeof fetch {
  return async (_url, init) => {
    const { id } = JSON.parse(String(init?.body));
    return Response.json({ jsonrpc: '2.0', ...payload, id }, { status });
  };
}

export function sseReply(frames: string | string[]): typeof fetch {
  return async (_url, init) => {
    const { id } = JSON.parse(String(init?.body));
    const encoder = new TextEncoder();
    const chunks = typeof frames === 'string' ? [frames] : frames;
    const stream = new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk.replaceAll('$id', id)));
        controller.close();
      },
    });
    return new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } });
  };
}
