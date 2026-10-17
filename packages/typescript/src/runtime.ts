import type { RequestHandler, Express } from 'express';
import type { Server } from 'node:http';

export interface RuntimeLimits {
  maxConcurrentRequests?: number;
  maxStreams?: number;
  bodyLimitBytes?: number;
  requestTimeoutMs?: number;
  executionTimeoutMs?: number;
  shutdownGraceMs?: number;
  maxPushConfigsPerTask?: number;
  maxTaskHistory?: number;
  maxEventsPerExecution?: number;
  maxOutputBytes?: number;
  maxTaskBytes?: number;
  maxStoredTasks?: number;
  maxConcurrentRequestsPerPrincipal?: number;
  maxStreamsPerPrincipal?: number;
}
export interface RuntimeStats {
  activeRequests: number;
  activeStreams: number;
  rejectedRequests: number;
  closing: boolean;
}
export type TelemetryObserver = (event: {
  name: 'request.accepted' | 'request.rejected' | 'request.finished' | 'runtime.stopping';
  stats: RuntimeStats;
}) => void;
export class RuntimeControl {
  readonly limits: Required<RuntimeLimits>;
  private readonly principals = new Map<string, { requests: number; streams: number }>();
  private state: RuntimeStats = { activeRequests: 0, activeStreams: 0, rejectedRequests: 0, closing: false };
  constructor(
    limits: RuntimeLimits = {},
    private readonly observer?: TelemetryObserver,
  ) {
    this.limits = {
      maxConcurrentRequests: 128,
      maxStreams: 32,
      bodyLimitBytes: 1048576,
      requestTimeoutMs: 60000,
      executionTimeoutMs: 60000,
      shutdownGraceMs: 5000,
      maxPushConfigsPerTask: 8,
      maxTaskHistory: 256,
      maxEventsPerExecution: 4096,
      maxOutputBytes: 1048576,
      maxTaskBytes: 4194304,
      maxStoredTasks: 10000,
      maxConcurrentRequestsPerPrincipal: 32,
      maxStreamsPerPrincipal: 8,
      ...limits,
    };
    for (const [key, value] of Object.entries(this.limits))
      if (!Number.isSafeInteger(value) || value < 1) throw new Error(`Invalid runtime limit: ${key}`);
  }
  get stats(): RuntimeStats {
    return { ...this.state };
  }
  private emit(name: Parameters<TelemetryObserver>[0]['name']): void {
    try {
      this.observer?.({ name, stats: this.stats });
    } catch {
      /* Observers do not alter execution. */
    }
  }
  stop(): void {
    this.state.closing = true;
    this.emit('runtime.stopping');
  }
  middleware: RequestHandler = (req, res, next) => {
    const principal = String(res.locals.a2aPrincipal ?? 'anonymous');
    const active = this.principals.get(principal) ?? { requests: 0, streams: 0 };
    const streaming =
      /(?:SendStreamingMessage|SubscribeToTask)/.test(String(req.body?.method)) ||
      /:(?:stream|subscribe)$/.test(req.path) ||
      req.headers.accept?.includes('text/event-stream') === true;
    if (
      this.state.closing ||
      active.requests >= this.limits.maxConcurrentRequestsPerPrincipal ||
      (streaming && active.streams >= this.limits.maxStreamsPerPrincipal) ||
      this.state.activeRequests >= this.limits.maxConcurrentRequests ||
      (streaming && this.state.activeStreams >= this.limits.maxStreams)
    ) {
      this.state.rejectedRequests++;
      this.emit('request.rejected');
      res.setHeader('Retry-After', '1');
      res.status(503).json({ error: 'Agent capacity unavailable' });
      return;
    }
    active.requests++;
    if (streaming) active.streams++;
    this.principals.set(principal, active);
    this.state.activeRequests++;
    if (streaming) this.state.activeStreams++;
    this.emit('request.accepted');
    let released = false;
    const timer = setTimeout(() => {
      if (!res.headersSent) res.status(504).json({ error: 'Request deadline exceeded' });
      else res.destroy();
    }, this.limits.requestTimeoutMs);
    timer.unref();
    const release = () => {
      if (released) return;
      released = true;
      clearTimeout(timer);
      active.requests--;
      if (streaming) active.streams--;
      if (!active.requests) this.principals.delete(principal);
      this.state.activeRequests--;
      if (streaming) this.state.activeStreams--;
      this.emit('request.finished');
    };
    res.once('finish', release);
    res.once('close', release);
    next();
  };
}

export interface AgentRuntime {
  readonly url: string;
  readonly closed: Promise<void>;
  readonly stats: RuntimeStats;
  stop(): Promise<void>;
}

/** A runtime owns its listener and closes resources once; it never installs process handlers. */
export async function startRuntime(
  app: Express,
  host: string,
  port: number,
  control: RuntimeControl,
  closeResources: () => Promise<void>,
): Promise<AgentRuntime> {
  let server: Server;
  try {
    server = await new Promise<Server>((resolve, reject) => {
      const listener = app.listen(port, host, (error?: Error) => {
        if (error) reject(error);
        else resolve(listener);
      });
      listener.once('error', reject);
    });
  } catch (error) {
    await closeResources();
    throw error;
  }
  const address = server.address();
  const actualPort = typeof address === 'object' && address ? address.port : port;
  const url = `http://${host.includes(':') ? `[${host}]` : host}:${actualPort}`;
  let resolveClosed!: () => void;
  const closed = new Promise<void>((resolve) => {
    resolveClosed = resolve;
  });
  let stopping: Promise<void> | undefined;
  return {
    url,
    closed,
    get stats() {
      return control.stats;
    },
    stop() {
      stopping ??= (async () => {
        control.stop();
        const stopped = new Promise<void>((resolve) => server.close(() => resolve()));
        let timer: ReturnType<typeof setTimeout>;
        const deadline = new Promise<never>((_resolve, reject) => {
          timer = setTimeout(() => {
            server.closeAllConnections();
            reject(new Error('Runtime shutdown deadline exceeded'));
          }, control.limits.shutdownGraceMs);
          timer.unref();
        });
        try {
          await Promise.race([Promise.all([closeResources(), stopped]), deadline]);
        } finally {
          clearTimeout(timer!);
          server.closeAllConnections();
          resolveClosed();
        }
      })();
      return stopping;
    },
  };
}
