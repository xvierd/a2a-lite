package com.a2alite.server;

import com.a2alite.Agent;
import com.a2alite.auth.AuthRequest;
import com.a2alite.auth.PrincipalIdentity;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.javalin.Javalin;
import io.javalin.config.JavalinConfig;
import io.javalin.http.Context;
import org.a2aproject.sdk.jsonrpc.common.json.JsonUtil;
import org.a2aproject.sdk.jsonrpc.common.wrappers.A2AErrorResponse;
import org.a2aproject.sdk.jsonrpc.common.wrappers.A2AResponse;
import org.a2aproject.sdk.jsonrpc.common.wrappers.SendStreamingMessageResponse;
import org.a2aproject.sdk.server.ServerCallContext;
import org.a2aproject.sdk.server.auth.AuthenticatedUser;
import org.a2aproject.sdk.server.auth.UnauthenticatedUser;
import org.a2aproject.sdk.server.extensions.A2AExtensions;
import org.a2aproject.sdk.spec.*;
import org.a2aproject.sdk.spec.InternalError;

import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.IntSupplier;

/** Javalin HTTP adapter backed by the official SDK's task lifecycle and JSON-RPC models. */
public class JavalinServerAdapter implements ServerAdapter {
    private final List<String> corsOrigins;
    private final ObjectMapper mapper = new ObjectMapper();
    private Javalin app;
    private SdkProtocol protocol;
    private RuntimeController controller;
    private com.a2alite.runtime.RuntimeLimits limits;

    public JavalinServerAdapter() { this(null); }

    public JavalinServerAdapter(List<String> corsOrigins) { this.corsOrigins = corsOrigins; }

    public static JavalinServerAdapter createIfAvailable() { return createIfAvailable(null); }

    public static JavalinServerAdapter createIfAvailable(List<String> corsOrigins) {
        try {
            Class.forName("io.javalin.Javalin");
            return new JavalinServerAdapter(corsOrigins);
        } catch (ClassNotFoundException e) {
            return null;
        }
    }

    @Override
    public void start(Agent agent, String host, int port) {
        try {
            app = Javalin.create(config -> {
                config.http.maxRequestSize = agent.getRuntimeOptions().limits().maxRequestBytes();
                register(config, agent, host, port, "", this::port);
            });
            app.start(host, port);
        } catch (RuntimeException failure) {
            stop();
            throw failure;
        }
    }

    /** Register a complete agent on the router's listener during Javalin configuration. */
    public static ServerAdapter mounted(JavalinConfig config, String prefix, List<String> corsOrigins,
                                        IntSupplier listeningPort) {
        return new JavalinServerAdapter(corsOrigins) {
            @Override public void start(Agent agent, String host, int port) {
                register(config, agent, host, port, prefix, listeningPort);
            }

            @Override public int port() { return listeningPort.getAsInt(); }
        };
    }

    final void register(JavalinConfig config, Agent agent, String host, int port, String prefix,
                        IntSupplier listeningPort) {
        String displayHost = "0.0.0.0".equals(host) ? "localhost" : host;
        limits = agent.getRuntimeOptions().limits();
        controller = new RuntimeController(limits);
        protocol = new SdkProtocol(agent, displayHost, port, prefix);
        String endpoint = prefix.isEmpty() ? "/" : prefix;
        String cardPath = prefix + "/.well-known/agent-card.json";
        String live = prefix + "/health/live";
        String health = prefix + "/health/ready";
        String metricsPath = prefix + "/metrics";
        config.routes.get(live, ctx -> ctx.json(Map.of("live", true)));
        config.routes.get(health, ctx -> {
            boolean ready = ready();
            ctx.status(ready ? 200 : 503).json(Map.of("ready", ready));
        });
        config.routes.get(metricsPath, ctx -> ctx.json(metrics()));
        config.routes.get(cardPath, ctx -> ctx.json(agent.buildAgentCardJson(displayHost, listeningPort.getAsInt(), prefix)));
        config.routes.post(endpoint, ctx -> handleRequest(ctx, agent));
        if (corsOrigins != null && !corsOrigins.isEmpty()) {
            for (String path : List.of(endpoint, cardPath, live, health, metricsPath))
                config.routes.before(path, this::addCorsHeaders);
            config.routes.options(endpoint, ctx -> ctx.status(204));
        }
    }

    /** Actual listening port, including when started with port zero. */
    public int port() { return app.port(); }

    @Override
    public void stop() {
        try {
            if (controller != null) controller.close();
        } finally {
            try {
                if (protocol != null) protocol.close();
            } finally {
                if (app != null) app.stop();
                protocol = null;
                app = null;
            }
        }
    }

    @Override public boolean ready() { return controller != null && controller.ready() && protocol != null && protocol.ready(); }
    @Override public Map<String, Object> metrics() { return controller == null ? Map.of() : controller.metrics(); }

    private void handleRequest(Context ctx, Agent agent) throws Exception {
        ctx.header("A2A-Version", "1.0");
        JsonNode id = mapper.nullNode();
        try {
            JsonNode body;
            try {
                var input = ctx.req().getInputStream();
                byte[] bytes = input.readNBytes(limits.maxRequestBytes());
                if (bytes.length == limits.maxRequestBytes() && input.read() != -1) {
                    ctx.status(413);
                    throw new InvalidRequestError("Request too large");
                }
                body = mapper.readTree(bytes);
            } catch (io.javalin.http.HttpResponseException e) {
                ctx.status(e.getStatus());
                throw new InvalidRequestError(e.getStatus() == 413 ? "Request too large" : "Invalid HTTP request");
            } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
                throw new JSONParseError();
            }
            if (body == null || !body.isObject()) throw new InvalidRequestError();
            id = body.path("id");
            if (id.isMissingNode()) id = mapper.nullNode();
            if (!id.isNull() && !id.isTextual() && !id.isNumber()) {
                id = mapper.nullNode();
                throw new InvalidRequestError();
            }
            if (!"2.0".equals(body.path("jsonrpc").asText()) || !body.path("method").isTextual()) {
                throw new InvalidRequestError();
            }
            Object correlation = id.isNumber() ? id.numberValue() : id.isTextual() ? id.textValue() : null;
            var headers = new HashMap<>(ctx.headerMap());
            var query = new HashMap<String, String>();
            ctx.queryParamMap().forEach((key, values) -> {
                if (!values.isEmpty()) query.put(key, values.get(0));
            });
            var auth = agent.getAuth().authenticate(new AuthRequest(headers, query));
            if (auth == null || !auth.authenticated() || (!auth.anonymous()
                    && (auth.userId() == null || auth.userId().isBlank()))) {
                ctx.status(401);
                respond(ctx, new A2AErrorResponse(correlation, new InvalidRequestError("Authentication required")), id);
                return;
            }
            JsonNode requestedTenant = body.path("params").path("tenant");
            if (!requestedTenant.isMissingNode() && !requestedTenant.isNull() && !requestedTenant.isTextual()) {
                throw new InvalidParamsError("Tenant must be a string");
            }
            String tenant = requestedTenant.asText("");
            if (!auth.authorizedTenants().contains(tenant) || (auth.anonymous() && !tenant.isEmpty())) {
                throw new TaskNotFoundError();
            }
            if (auth.anonymous() && agent.getRuntimeOptions().profile() != com.a2alite.runtime.RuntimeOptions.Profile.LEARNING) {
                ctx.status(401); throw new InvalidRequestError("Identified authentication required");
            }
            var user = auth.anonymous() ? UnauthenticatedUser.INSTANCE
                : new AuthenticatedUser(PrincipalIdentity.subject(auth));
            String extensionHeader = ctx.header("A2A-Extensions");
            var context = new ServerCallContext(user,
                Map.of(ServerCallContext.TRANSPORT_KEY, TransportProtocol.JSONRPC, TaskOwnership.TENANT_KEY, tenant),
                A2AExtensions.getRequestedExtensions(extensionHeader == null ? List.of() : List.of(extensionHeader)),
                ctx.header("A2A-Version"));
            String method = body.path("method").asText();
            JsonNode params = body.path("params");
            for (var value : List.of(params.path("historyLength"), params.path("configuration").path("historyLength"), params.path("pageSize"))) {
                if (!value.isMissingNode() && !value.isNull() && (!value.canConvertToInt() || value.asInt() < 0
                        || value.asInt() > limits.maxHistoryLength())) throw new InvalidParamsError("History or page limit exceeded");
            }
            boolean sending = method.equals("SendMessage") || method.equals("SendStreamingMessage");
            boolean streaming = method.equals("SendStreamingMessage") || method.equals("SubscribeToTask");
            try (var streamLease = streaming ? controller.admitStream(context) : null;
                 var taskLease = sending ? controller.admitTask(context) : null) {
                Object result;
                try { result = protocol.dispatch(method, params, correlation, context); }
                catch (RuntimeException failure) { if (taskLease != null) taskLease.abort(); throw failure; }
                if (result instanceof Flow.Publisher<?> publisher) {
                    @SuppressWarnings("unchecked")
                    var events = (Flow.Publisher<StreamingEventKind>) publisher;
                    stream(ctx, events, correlation, id, context);
                } else {
                    respond(ctx, (A2AResponse<?>) result, id);
                }
            }
        } catch (RuntimeOverloadedException e) {
            ctx.status(503).header("Retry-After", "1");
            respond(ctx, new A2AErrorResponse(null, new InternalError("Runtime capacity unavailable")), id);
        } catch (A2AError e) {
            respond(ctx, new A2AErrorResponse(null, e), id);
        } catch (IllegalArgumentException e) {
            respond(ctx, new A2AErrorResponse(null, new InvalidParamsError("Invalid request parameters")), id);
        } catch (Exception e) {
            respond(ctx, new A2AErrorResponse(null, new InternalError("Request failed")), id);
        }
    }

    private String encode(A2AResponse<?> response, JsonNode id) throws Exception {
        var json = (ObjectNode) mapper.readTree(JsonUtil.toJson(response));
        json.set("id", id);
        if (response.getError() == null && response.getResult() == null) json.putObject("result");
        return mapper.writeValueAsString(json);
    }

    private void respond(Context ctx, A2AResponse<?> response, JsonNode id) throws Exception {
        if (!ctx.res().isCommitted()) ctx.contentType("application/json").result(encode(response, id));
    }

    private void stream(Context ctx, Flow.Publisher<StreamingEventKind> publisher, Object correlation,
                        JsonNode id, ServerCallContext context) throws Exception {
        ctx.contentType("text/event-stream");
        ctx.header("Cache-Control", "no-cache");
        ctx.header("X-Accel-Buffering", "no");
        var done = new CountDownLatch(1);
        var subscription = new AtomicReference<Flow.Subscription>();
        publisher.subscribe(new Flow.Subscriber<>() {
            @Override
            public void onSubscribe(Flow.Subscription value) {
                subscription.set(value);
                value.request(1);
            }

            @Override
            public void onNext(StreamingEventKind event) {
                try {
                    write(new SendStreamingMessageResponse(correlation, event));
                    subscription.get().request(1);
                } catch (Exception e) {
                    subscription.get().cancel();
                    context.invokeEventConsumerCancelCallback();
                    done.countDown();
                }
            }

            private void write(A2AResponse<?> response) throws Exception {
                byte[] data = ("data: " + encode(response, id) + "\n\n").getBytes(StandardCharsets.UTF_8);
                ctx.res().getOutputStream().write(data);
                ctx.res().getOutputStream().flush();
            }

            @Override
            public void onError(Throwable error) {
                try {
                    write(new A2AErrorResponse(correlation,
                        error instanceof A2AError a2a ? a2a : new InternalError("Stream failed")));
                } catch (Exception ignored) {
                    // The client may have disconnected.
                } finally {
                    done.countDown();
                }
            }

            @Override
            public void onComplete() { done.countDown(); }
        });
        try {
            done.await(limits.streamTimeout().toNanos(), TimeUnit.NANOSECONDS);
        } finally {
            if (subscription.get() != null) subscription.get().cancel();
            context.invokeEventConsumerCancelCallback();
        }
    }

    private void addCorsHeaders(Context ctx) {
        if (corsOrigins == null || corsOrigins.isEmpty()) return;
        String origin = ctx.header("Origin");
        ctx.header("Vary", "Origin");
        if (origin != null && (corsOrigins.contains("*") || corsOrigins.contains(origin))) {
            ctx.header("Access-Control-Allow-Origin", origin);
            ctx.header("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
            ctx.header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key, A2A-Version, A2A-Extensions");
            ctx.header("Access-Control-Expose-Headers", "A2A-Version, A2A-Extensions");
        }
    }
}
