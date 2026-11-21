package com.a2alite.server;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import org.a2aproject.sdk.spec.Task;
import org.a2aproject.sdk.spec.TaskPushNotificationConfig;
import org.a2aproject.sdk.spec.TaskState;
import org.a2aproject.sdk.spec.Message;
import org.a2aproject.sdk.spec.TaskStatus;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import static org.assertj.core.api.Assertions.*;

class SdkPushSenderTest {
    private final Task task = Task.builder().id("task-id").contextId("ctx")
        .status(new TaskStatus(TaskState.TASK_STATE_WORKING)).build();

    @Test
    void reportsEmptySuccessfulPartialAndFailedDeliveries() throws Exception {
        var received = new CopyOnWriteArrayList<String>();
        var peer = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        peer.createContext("/", exchange -> {
            try (exchange) {
                String path = exchange.getRequestURI().getPath();
                var body = new ObjectMapper().readTree(exchange.getRequestBody());
                received.add(path + ":" + exchange.getRequestHeaders().getFirst("X-A2A-Notification-Token")
                    + ":" + body.at("/task/id").asText());
                exchange.sendResponseHeaders(path.startsWith("/ok") ? 204 : 503, -1);
            }
        });
        peer.start();
        try (var backend = new InMemoryProtocolBackend()) {
            var http = HttpClient.newHttpClient();
            // Only the test transport accepts a loopback receiver. Real callbacks use pinned public HTTPS.
            var sender = SdkPushSender.forBackend(backend, (url, payload, headers) -> {
                var req = HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofString(payload));
                headers.forEach(req::header);
                try {
                    if (http.send(req.build(), HttpResponse.BodyHandlers.discarding()).statusCode() != 204)
                        throw new IOException("Delivery failed");
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IOException(e);
                }
            });
            assertThat(sender.sendNotification(task, task)).isTrue();
            assertThat(sender.sendNotification(Message.builder().role(Message.Role.ROLE_AGENT)
                .messageId("message").parts(new org.a2aproject.sdk.spec.TextPart("hello")).build(), null)).isTrue();
            assertThat(received).isEmpty();
            var configs = backend.pushConfigs();
            String root = "http://127.0.0.1:" + peer.getAddress().getPort();
            for (String target : List.of("ok", "ok2")) {
                configs.setInfo(TaskPushNotificationConfig.builder().taskId(task.id()).id(target)
                    .url(root + "/" + target).token(target).build());
            }
            assertThat(sender.sendNotification(task, null)).isTrue();
            assertThat(received).containsExactlyInAnyOrder("/ok:ok:task-id", "/ok2:ok2:task-id");

            configs.setInfo(TaskPushNotificationConfig.builder().taskId(task.id()).id("fail")
                .url(root + "/fail").token("failed").build());
            received.clear();
            assertThat(sender.sendNotification(task, task)).isFalse();
            assertThat(received).containsExactlyInAnyOrder("/ok:ok:task-id", "/ok2:ok2:task-id", "/fail:failed:task-id");

            configs.deleteInfo(task.id(), "ok");
            configs.deleteInfo(task.id(), "ok2");
            received.clear();
            assertThat(sender.sendNotification(task, task)).isFalse();
            assertThat(received).containsExactly("/fail:failed:task-id");
        } finally {
            peer.stop(0);
        }
    }

    @Test
    void durableSenderAcknowledgesHandoffWithoutPosting() {
        var durable = new com.a2alite.persistence.JdbcProtocolBackend(
            new org.postgresql.ds.PGSimpleDataSource(),
            new com.a2alite.persistence.CallbackKeyring("fixture", java.util.Map.of("fixture",
                new javax.crypto.spec.SecretKeySpec(new byte[32], "AES"))),
            com.a2alite.runtime.RuntimeLimits.defaults(), false);
        try (durable) {
            var posts = new ArrayList<String>();
            var sender = SdkPushSender.forBackend(durable, (url, body, headers) -> posts.add(url));
            assertThat(sender.sendNotification(task, task)).isTrue();
            assertThat(posts).isEmpty();
        }
    }
}
