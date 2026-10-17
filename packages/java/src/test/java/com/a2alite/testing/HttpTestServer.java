package com.a2alite.testing;

import io.javalin.Javalin;
import io.javalin.http.Handler;
import java.util.concurrent.atomic.AtomicReference;

/** Routes are fixed at startup; tests replace only the response behavior of their local peer. */
public final class HttpTestServer {
    private final AtomicReference<Handler> post = new AtomicReference<>(ctx -> ctx.status(404));
    private final AtomicReference<Handler> get = new AtomicReference<>(ctx -> ctx.status(404));
    private final Javalin server = Javalin.create(config -> {
        config.routes.post("/", ctx -> post.get().handle(ctx));
        config.routes.get("/.well-known/agent-card.json", ctx -> get.get().handle(ctx));
    });
    public static HttpTestServer create() { return new HttpTestServer(); }
    public HttpTestServer start(int port) { server.start("127.0.0.1", port); return this; }
    public int port() { return server.port(); }
    public void stop() { server.stop(); }
    public void post(String path, Handler handler) {
        if (!"/".equals(path)) throw new IllegalArgumentException("Unexpected fixture route");
        post.set(handler);
    }
    public void get(String path, Handler handler) {
        if (!"/.well-known/agent-card.json".equals(path)) throw new IllegalArgumentException("Unexpected fixture route");
        get.set(handler);
    }
}
