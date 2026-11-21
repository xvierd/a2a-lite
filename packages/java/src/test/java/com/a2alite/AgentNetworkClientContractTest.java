package com.a2alite;

import com.a2alite.errors.RemoteAgentException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestFactory;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Stream;

import static org.assertj.core.api.Assertions.*;

class AgentNetworkClientContractTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    private final java.util.concurrent.ExecutorService workers = Executors.newCachedThreadPool();
    private final AgentNetwork network = new AgentNetwork();
    private HttpServer server;
    private String base;

    @BeforeEach
    void start() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.setExecutor(workers);
        server.start();
        base = "http://127.0.0.1:" + server.getAddress().getPort();
    }

    @AfterEach
    void stop() {
        server.stop(0);
        workers.shutdownNow();
    }

    private static void reply(HttpExchange exchange, String mime, String body) throws IOException {
        var bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", mime);
        exchange.sendResponseHeaders(200, bytes.length);
        try (var out = exchange.getResponseBody()) { out.write(bytes); }
    }

    private static String result(JsonNode request, Object value) throws IOException {
        return JSON.writeValueAsString(Map.of("jsonrpc", "2.0", "id", request.get("id"), "result", value));
    }

    private static Map<String, Object> status(String taskId, String state) {
        return Map.of("statusUpdate", Map.of("taskId", taskId, "status", Map.of("state", state)));
    }

    private static Map<String, Object> snapshot(String taskId, String state) {
        return Map.of("task", Map.of("id", taskId, "status", Map.of("state", state)));
    }

    private static String frame(JsonNode request, Object value) throws IOException {
        return "data: " + result(request, value) + "\n\n";
    }

    private static Map<String, Object> message(String text) {
        return Map.of("message", Map.of("messageId", "m1", "role", "ROLE_AGENT", "parts", List.of(Map.of("text", text))));
    }

    @Test
    void selectedPathTenantAndRotatingCredentialsFollowCallsPagesAndHandles() throws Exception {
        var currentKey = new AtomicReference<>("first");
        var blueTenant = new AtomicReference<>("blue");
        var methods = new java.util.concurrent.ConcurrentLinkedQueue<String>();
        for (var name : List.of("blue", "green")) {
            var discoveryUrl = base + "/agents/" + name;
            network.withCredentials(discoveryUrl, ignored -> Map.of("X-Key", name + "-" + currentKey.get()));
            server.createContext("/agents/" + name + "/.well-known/agent-card.json", exchange -> {
                String tenant = name.equals("blue") ? blueTenant.get() : name;
                if (!exchange.getRequestHeaders().getFirst("X-Key").equals(name + "-" + currentKey.get())) {
                    exchange.sendResponseHeaders(403, -1);
                    exchange.close();
                    return;
                }
                reply(exchange, "application/json", JSON.writeValueAsString(Map.of("supportedInterfaces", List.of(
                    Map.of("protocolBinding", "HTTP+JSON", "protocolVersion", "1.0", "url", base + "/rest"),
                    Map.of("protocolBinding", "JSONRPC", "protocolVersion", "2.0", "url", base + "/v2"),
                    Map.of("protocolBinding", "JSONRPC", "protocolVersion", "1.0.1", "url", base + "/rpc/", "tenant", tenant)
                ))));
            });
            network.add(name, discoveryUrl, true);
        }
        server.createContext("/rpc/", exchange -> {
            var body = JSON.readTree(exchange.getRequestBody());
            var params = body.get("params");
            var tenant = params.path("tenant").asText();
            var key = exchange.getRequestHeaders().getFirst("X-Key");
            if (!(tenant + "-" + currentKey.get()).equals(key)) {
                exchange.sendResponseHeaders(401, -1);
                exchange.close();
                return;
            }
            var method = body.get("method").asText();
            methods.add(method);
            var task = Map.of("id", tenant + "-task", "status", Map.of("state", "TASK_STATE_WORKING"));
            if (method.equals("SubscribeToTask")) {
                reply(exchange, "text/event-stream", frame(body, snapshot(params.get("id").asText(), "TASK_STATE_COMPLETED")));
                return;
            }
            Object value = switch (method) {
                case "SendMessage" -> Map.of("task", task);
                case "GetTask", "CancelTask" -> task;
                case "ListTasks" -> {
                    boolean last = "next/=?".equals(params.path("pageToken").asText());
                    if (last) yield Map.of("tasks", List.of(Map.of("id", "b")), "totalSize", 2, "pageSize", 1);
                    yield Map.of("tasks", List.of(Map.of("id", "a")), "nextPageToken", "next/=?");
                }
                default -> Map.of();
            };
            reply(exchange, "application/json", result(body, value));
        });

        var blue = workers.submit(() -> network.callWithHandle("blue", "task", Map.of(), 5));
        var green = workers.submit(() -> network.callWithHandle("green", "task", Map.of(), 5));
        var handle = blue.get(5, TimeUnit.SECONDS);
        assertThat(green.get(5, TimeUnit.SECONDS).getTaskId()).isEqualTo("green-task");
        assertThat(handle.getTenant()).isEqualTo("blue");
        assertThat(handle.getAgentUrl()).isEqualTo(base + "/rpc/");
        assertThat(network.getCard("blue").orElseThrow().getTenant()).isEqualTo("blue");

        var page = network.listTasks("blue", 1, null);
        assertThat(page.tasks()).extracting(task -> task.get("id")).containsExactly("a");
        var lastPage = network.listTasks("blue", 1, page.nextPageToken());
        assertThat(lastPage.tasks()).extracting(task -> task.get("id")).containsExactly("b");
        assertThat(lastPage.nextPageToken()).isEmpty();

        currentKey.set("rotated");
        blueTenant.set("changed");
        assertThat(network.discoverNamed("blue").getTenant()).isEqualTo("changed");
        assertThat(handle.get()).containsEntry("id", "blue-task");
        assertThat(handle.getStatus()).isInstanceOf(Map.class);
        handle.subscribe("https://example.test/hook");
        handle.getPushConfig();
        handle.unsubscribe();
        try (var events = handle.subscribeEvents()) {
            assertThat(events).containsExactly(snapshot("blue-task", "TASK_STATE_COMPLETED"));
        }
        handle.cancel();
        assertThat(methods).contains("SendMessage", "GetTask", "CancelTask", "SubscribeToTask", "ListTasks",
            "CreateTaskPushNotificationConfig", "GetTaskPushNotificationConfig", "DeleteTaskPushNotificationConfig");
    }

    @Test
    void discoveryRejectsAnIncompatibleCardWithoutRegisteringOrForwardingCredentials() {
        server.createContext("/.well-known/agent-card.json", exchange -> reply(exchange, "application/json",
            JSON.writeValueAsString(Map.of("supportedInterfaces", List.of(
                Map.of("protocolBinding", "JSONRPC", "protocolVersion", "1.0", "url", "https://elsewhere.invalid/rpc"),
                Map.of("protocolBinding", "HTTP+JSON", "protocolVersion", "1.0", "url", base + "/rest")
            )))));
        network.withHeaders(base, Map.of("Authorization", "Bearer test"));
        assertThatThrownBy(() -> network.add("unsafe", base, true)).hasMessageContaining("same-origin");
        assertThat(network.get("unsafe")).isEmpty();
    }

    @Test
    void explicitTenantIsScopedPerCaller() throws Exception {
        server.createContext("/", exchange -> {
            var body = JSON.readTree(exchange.getRequestBody());
            reply(exchange, "application/json", result(body, message(body.path("params").path("tenant").asText("default"))));
        });
        var blue = workers.submit(() -> network.withTenant("blue").callRemoteSkill(base, "task", Map.of(), 5));
        var green = workers.submit(() -> network.withTenant("green").callRemoteSkill(base, "task", Map.of(), 5));
        assertThat(blue.get(5, TimeUnit.SECONDS)).isEqualTo("blue");
        assertThat(green.get(5, TimeUnit.SECONDS)).isEqualTo("green");
        assertThat(network.callRemoteSkill(base, "task", Map.of(), 5)).isEqualTo("default");
    }

    @Test
    void callersSelectDifferentAdvertisedTenantsAndPathsFromOneCachedCard() throws Exception {
        server.createContext("/.well-known/agent-card.json", exchange -> reply(exchange, "application/json",
            JSON.writeValueAsString(Map.of("supportedInterfaces", List.of(
                Map.of("protocolBinding", "JSONRPC", "protocolVersion", "1.0", "url", base + "/blue", "tenant", "blue"),
                Map.of("protocolBinding", "JSONRPC", "protocolVersion", "1.0", "url", base + "/green", "tenant", "green")
            )))));
        server.createContext("/", exchange -> {
            var req = JSON.readTree(exchange.getRequestBody());
            var destination = exchange.getRequestURI().getPath() + ":" + req.path("params").path("tenant").asText();
            reply(exchange, "application/json", result(req, message(destination)));
        });
        network.add("worker", base);
        assertThat(network.withTenant("green").discoverNamed("worker").getUrl()).isEqualTo(base + "/green");
        var green = workers.submit(() -> network.withTenant("green").call("worker", "s", Map.of()));
        var blue = workers.submit(() -> network.withTenant("blue").call("worker", "s", Map.of()));
        assertThat(green.get(5, TimeUnit.SECONDS)).isEqualTo("/green:green");
        assertThat(blue.get(5, TimeUnit.SECONDS)).isEqualTo("/blue:blue");
        assertThat(network.call("worker", "s", Map.of())).isEqualTo("/blue:blue");
        assertThat(network.withTenant("green").getCard("worker").orElseThrow().getTenant()).isEqualTo("green");
        assertThatThrownBy(() -> network.withTenant("unknown").call("worker", "s", Map.of()))
            .hasMessageContaining("requested tenant");
    }

    @Test
    void discoveredTenantlessInterfaceOmitsManualTenantForDelegationAndFollowUp() throws Exception {
        server.createContext("/public/.well-known/agent-card.json", exchange -> reply(exchange, "application/json",
            JSON.writeValueAsString(Map.of("supportedInterfaces", List.of(Map.of("protocolBinding", "JSONRPC",
                "protocolVersion", "1.0", "url", base + "/rpc"))))));
        var observed = new java.util.concurrent.ConcurrentLinkedQueue<String>();
        server.createContext("/rpc", exchange -> {
            var req = JSON.readTree(exchange.getRequestBody());
            var params = req.get("params");
            observed.add(params.has("tenant") ? params.get("tenant").asText() : "omitted");
            var method = req.path("method").asText();
            var task = Map.of("id", "t", "status", Map.of("state", "TASK_STATE_WORKING"));
            if (method.equals("SubscribeToTask")) {
                reply(exchange, "text/event-stream", frame(req, snapshot("t", "TASK_STATE_COMPLETED")));
            } else reply(exchange, "application/json", result(req, method.equals("SendMessage") ? Map.of("task", task) : task));
        });

        var scoped = network.withTenant("blue");
        scoped.add("public", base + "/public", true);
        var agent = Agent.builder().name("caller").description("caller").network(scoped).build();
        var blue = workers.submit(() -> agent.delegateWithHandle("public", "task", Map.of(), 5));
        var green = workers.submit(() -> network.withTenant("green").callWithHandle("public", "task", Map.of(), 5));
        var handle = blue.get(5, TimeUnit.SECONDS);
        assertThat(handle.getTenant()).isNull();
        assertThat(green.get(5, TimeUnit.SECONDS).getTenant()).isNull();
        handle.get();
        try (var events = handle.subscribeEvents()) { assertThat(events).hasSize(1); }
        assertThat(observed).containsExactly("omitted", "omitted", "omitted", "omitted");

        scoped.callRemoteSkill(base + "/rpc", "task", Map.of(), 5);
        assertThat(observed).endsWith("blue");
    }

    @TestFactory
    Stream<DynamicTest> malformedResponsesFailForSendGetAndStreaming() {
        return Stream.of("wrong version", "wrong id", "missing result and error", "both result and error", "malformed error")
            .map(defect -> DynamicTest.dynamicTest(defect, () -> {
                server.createContext("/", exchange -> {
                    var req = JSON.readTree(exchange.getRequestBody());
                    var fields = JSON.createObjectNode().put("jsonrpc", "2.0");
                    fields.set("id", req.get("id"));
                    fields.putObject("result").put("id", "t");
                    switch (defect) {
                        case "wrong version" -> fields.put("jsonrpc", "1.0");
                        case "wrong id" -> fields.put("id", 1);
                        case "missing result and error" -> fields.remove("result");
                        case "both result and error" -> fields.putObject("error").put("message", "oops").put("code", -1);
                        case "malformed error" -> {
                            fields.remove("result");
                            fields.putObject("error").put("code", "bad");
                        }
                    }
                    if (req.get("method").asText().equals("SendStreamingMessage")) {
                        reply(exchange, "text/event-stream", "data: " + fields + "\n\n");
                    } else reply(exchange, "application/json", fields.toString());
                });
                try {
                    assertThatThrownBy(() -> network.callRemoteSkill(base, "s", Map.of(), 5)).isInstanceOf(RemoteAgentException.class)
                        .hasMessageContaining("JSON-RPC");
                    assertThatThrownBy(() -> network.getRemoteTaskSnapshot(base, "t", 5)).isInstanceOf(RemoteAgentException.class)
                        .hasMessageContaining("JSON-RPC");
                    try (var stream = network.streamEvents(base, "s", Map.of())) {
                        assertThatThrownBy(() -> stream.iterator().next()).isInstanceOf(RemoteAgentException.class)
                            .hasMessageContaining("JSON-RPC");
                    }
                } finally {
                    server.removeContext("/");
                }
            }));
    }

    @Test
    void sseHonorsCrLfCrLfPairsMultilineUtf8AndStructuredParts() throws Exception {
        Map<String, Object> artifact = Map.of("artifactUpdate", Map.of("taskId", "t", "append", true, "artifact", Map.of(
            "artifactId", "a", "metadata", Map.of("source", "λ"), "parts", List.of(Map.of("text", "café 🌈"),
            Map.of("data", Map.of("value", 1))))));
        var finished = status("t", "TASK_STATE_INPUT_REQUIRED");
        server.createContext("/", exchange -> {
            var req = JSON.readTree(exchange.getRequestBody());
            var first = result(req, artifact).replaceFirst(",", ",\rdata: ");
            String wire = "\uFEFF: keepalive\r\r" + frame(req, snapshot("t", "TASK_STATE_WORKING")) + "data: " + first + "\r\r" +
                "event: message\r\ndata: " + result(req, finished) + "\r\n\r\n";
            exchange.getResponseHeaders().set("Content-Type", "TEXT/Event-Stream; charset=utf-8");
            exchange.sendResponseHeaders(200, 0);
            try (var out = exchange.getResponseBody()) {
                for (byte b : wire.getBytes(StandardCharsets.UTF_8)) {
                    out.write(b);
                    out.flush();
                }
            }
        });
        try (var events = network.subscribeTask(base, "t")) {
            assertThat(events).containsExactly(snapshot("t", "TASK_STATE_WORKING"), artifact, finished);
        }
        try (var text = network.streamRemoteSkill(base, "s", Map.of())) {
            assertThat(text).containsExactly("café 🌈");
        }
    }

    @Test
    void directMessagePreservesNonTextPartsAndMetadata() throws Exception {
        var event = Map.of("message", Map.of("role", "ROLE_AGENT", "messageId", "m", "metadata", Map.of("vendor", 2),
            "parts", List.of(Map.of("url", "https://example.test/photo", "mediaType", "image/jpeg"))));
        server.createContext("/", exchange -> reply(exchange, "text/event-stream",
            "data: " + result(JSON.readTree(exchange.getRequestBody()), event) + "\n\n"));
        try (var stream = network.streamEvents(base, "m", Map.of())) {
            var iterator = stream.iterator();
            assertThat(iterator.next()).isEqualTo(event);
            assertThat(iterator.hasNext()).isFalse();
            assertThat(iterator.hasNext()).isFalse();
        }
    }

    @Test
    void jsonBeforeStreamAndErrorAfterChunkPreserveErrorCodeAndData() throws Exception {
        server.createContext("/", exchange -> {
            var req = JSON.readTree(exchange.getRequestBody());
            var error = Map.of("jsonrpc", "2.0", "id", req.get("id"),
                "error", Map.of("code", -32001, "message", "peer failed", "data", Map.of("retry", false)));
            if (exchange.getRequestURI().getPath().equals("/early")) {
                reply(exchange, "Application/JSON; charset=UTF-8", JSON.writeValueAsString(error));
            } else {
                String chunk = result(req, Map.of("artifactUpdate", Map.of("artifact", Map.of("parts", List.of(Map.of("text", "once"))))));
                reply(exchange, "text/event-stream", "data: " + chunk + "\n\n" + "data: " + JSON.writeValueAsString(error) + "\n\n");
            }
        });
        for (String path : List.of("/early", "/late")) {
            try (var stream = network.streamRemoteSkill(base + path, "s", Map.of())) {
                var iterator = stream.iterator();
                if (path.equals("/late")) assertThat(iterator.next()).isEqualTo("once");
                var failure = catchThrowableOfType(iterator::hasNext, RemoteAgentException.class);
                assertThat(failure).hasMessageContaining("peer failed");
                assertThat(failure.getCode()).isEqualTo(-32001);
                assertThat(failure.getData()).isEqualTo(Map.of("retry", false));
                assertThat(iterator.hasNext()).isFalse();
            }
        }
    }

    @Test
    void openSubscriptionFollowsResumedTaskAndReturnsAtTerminalBeforePeerEof() throws Exception {
        var releasePeer = new CountDownLatch(1);
        var states = List.of("TASK_STATE_AUTH_REQUIRED", "TASK_STATE_WORKING", "TASK_STATE_INPUT_REQUIRED",
            "TASK_STATE_WORKING", "TASK_STATE_COMPLETED");
        server.createContext("/", exchange -> {
            var req = JSON.readTree(exchange.getRequestBody());
            exchange.getResponseHeaders().set("Content-Type", "text/event-stream");
            exchange.sendResponseHeaders(200, 0);
            try (var out = exchange.getResponseBody()) {
                out.write(frame(req, snapshot("t", "TASK_STATE_SUBMITTED")).getBytes(StandardCharsets.UTF_8));
                for (String state : states) {
                    out.write(("data: " + result(req, status("t", state)) + "\n\n").getBytes(StandardCharsets.UTF_8));
                }
                out.flush();
                releasePeer.await(10, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        try (var stream = network.subscribeTask(base, "t")) {
            var collected = workers.submit(() -> {
                var events = new java.util.ArrayList<Map<String, Object>>();
                stream.forEach(events::add);
                return events;
            });
            var events = collected.get(5, TimeUnit.SECONDS);
            assertThat(events.get(0)).isEqualTo(snapshot("t", "TASK_STATE_SUBMITTED"));
            assertThat(events.subList(1, events.size())).isEqualTo(states.stream().map(s -> status("t", s)).toList());
        } finally {
            releasePeer.countDown();
        }
    }

    @Test
    void prematureEofDoesNotDispatchAnUnterminatedFinalEvent() throws Exception {
        server.createContext("/", exchange -> {
            var req = JSON.readTree(exchange.getRequestBody());
            reply(exchange, "text/event-stream", frame(req, snapshot("t", "TASK_STATE_WORKING")) +
                "data: " + result(req, status("t", "TASK_STATE_COMPLETED")) + "\n");
        });
        try (var stream = network.subscribeTask(base, "t")) {
            var iterator = stream.iterator();
            assertThat(iterator.next()).isEqualTo(snapshot("t", "TASK_STATE_WORKING"));
            assertThatThrownBy(iterator::hasNext).isInstanceOf(RemoteAgentException.class).hasMessageContaining("ended before");
            assertThat(iterator.hasNext()).isFalse();
        }
    }

    @Test
    void subscriptionValidatesFirstSnapshotAndEveryResourceIdAfterRpcErrors() {
        server.createContext("/", exchange -> {
            var req = JSON.readTree(exchange.getRequestBody());
            String path = exchange.getRequestURI().getPath();
            var working = snapshot("t", "TASK_STATE_WORKING");
            String frames = switch (path) {
                case "/initial-error" -> "data: " + JSON.writeValueAsString(Map.of("jsonrpc", "2.0", "id", req.get("id"),
                    "error", Map.of("code", -32001, "message", "missing task"))) + "\n\n";
                case "/first-message" -> frame(req, message("bad"));
                case "/first-update" -> frame(req, status("t", "TASK_STATE_COMPLETED"));
                case "/wrong-snapshot" -> frame(req, snapshot("other", "TASK_STATE_WORKING"));
                case "/wrong-update" -> frame(req, working) + frame(req, status("other", "TASK_STATE_COMPLETED"));
                default -> frame(req, working) + frame(req, Map.of("artifactUpdate", Map.of("taskId", "other")));
            };
            reply(exchange, "text/event-stream", frames);
        });
        for (var path : List.of("/initial-error", "/first-message", "/first-update", "/wrong-snapshot", "/wrong-update", "/wrong-artifact")) {
            try (var events = network.subscribeTask(base + path, "t")) {
                var iterator = events.iterator();
                if (path.equals("/wrong-update") || path.equals("/wrong-artifact")) {
                    assertThat(iterator.next()).isEqualTo(snapshot("t", "TASK_STATE_WORKING"));
                }
                var failure = catchThrowableOfType(iterator::hasNext, RemoteAgentException.class);
                assertThat(failure).as(path).isNotNull();
                if (path.equals("/initial-error")) assertThat(failure.getCode()).isEqualTo(-32001);
                else if (path.startsWith("/first")) assertThat(failure).hasMessageContaining("begin with a Task");
                else assertThat(failure).hasMessageContaining("requested Task");
                assertThat(iterator.hasNext()).isFalse();
            }
        }
    }

    @Test
    void closingSubscriptionReleasesReaderAndHttpBody() throws Exception {
        var allowWrites = new CountDownLatch(1);
        var peerDisconnected = new CountDownLatch(1);
        server.createContext("/", exchange -> {
            var req = JSON.readTree(exchange.getRequestBody());
            exchange.getResponseHeaders().set("Content-Type", "text/event-stream");
            exchange.sendResponseHeaders(200, 0);
            try (var out = exchange.getResponseBody()) {
                out.write(frame(req, snapshot("t", "TASK_STATE_WORKING")).getBytes(StandardCharsets.UTF_8));
                out.flush();
                if (allowWrites.await(5, TimeUnit.SECONDS)) {
                    byte[] padding = (":" + " ".repeat(8192) + "\n").getBytes(StandardCharsets.UTF_8);
                    for (int i = 0; i < 2048; i++) { out.write(padding); out.flush(); }
                }
            } catch (IOException disconnected) {
                peerDisconnected.countDown();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        try (var events = network.subscribeTask(base, "t")) {
            var iter = events.iterator();
            assertThat(iter.next()).isEqualTo(snapshot("t", "TASK_STATE_WORKING"));
            var next = workers.submit(iter::hasNext);
            events.close();
            allowWrites.countDown();
            assertThat(next.get(5, TimeUnit.SECONDS)).isFalse();
            assertThat(peerDisconnected.await(5, TimeUnit.SECONDS)).isTrue();
        }
    }

    @Test
    void closingBeforeHttpHeadersCancelsThePendingExchange() {
        var pending = new CompletableFuture<java.net.http.HttpResponse<java.io.InputStream>>();
        var events = new TaskEventStream(pending, "id", null);
        events.close();
        assertThat(pending.isCancelled()).isTrue();
        assertThat(events.iterator().hasNext()).isFalse();
    }
}
