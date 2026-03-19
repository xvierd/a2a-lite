package com.a2alite.push;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.security.InvalidKeyException;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * Tests for {@link WebhookPushNotifier} using JDK's built-in HTTP server.
 *
 * No extra dependencies needed — {@code com.sun.net.httpserver.HttpServer} is
 * part of the JDK and available in Java 11+.
 */
class WebhookPushNotifierTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final String SECRET = "test-secret-key";
    private static final String HMAC_ALGORITHM = "HmacSHA256";

    private HttpServer server;
    private int port;
    private String baseUrl;

    // Captures from the most recent request
    private final AtomicReference<String> lastMethod = new AtomicReference<>();
    private final AtomicReference<String> lastContentType = new AtomicReference<>();
    private final AtomicReference<String> lastSignatureHeader = new AtomicReference<>();
    private final AtomicReference<String> lastBody = new AtomicReference<>();
    private final AtomicInteger responseStatus = new AtomicInteger(200);
    private final AtomicInteger requestCount = new AtomicInteger(0);
    private CountDownLatch requestLatch;

    @BeforeEach
    void startServer() throws IOException {
        server = HttpServer.create(new InetSocketAddress(0), 0);
        port = server.getAddress().getPort();
        baseUrl = "http://localhost:" + port;
        requestLatch = new CountDownLatch(1);

        server.createContext("/hook", this::handleHook);
        server.createContext("/slow", this::handleHook); // reuse same handler
        server.start();
    }

    @AfterEach
    void stopServer() {
        if (server != null) {
            server.stop(0);
        }
    }

    // -------------------------------------------------------------------------
    // Test server handler
    // -------------------------------------------------------------------------

    private void handleHook(HttpExchange exchange) throws IOException {
        lastMethod.set(exchange.getRequestMethod());
        lastContentType.set(exchange.getRequestHeaders().getFirst("Content-Type"));
        lastSignatureHeader.set(exchange.getRequestHeaders().getFirst("X-A2A-Signature"));

        try (InputStream is = exchange.getRequestBody()) {
            lastBody.set(new String(is.readAllBytes(), StandardCharsets.UTF_8));
        }

        requestCount.incrementAndGet();
        requestLatch.countDown();

        int status = responseStatus.get();
        byte[] resp = status >= 400
            ? ("error " + status).getBytes(StandardCharsets.UTF_8)
            : "ok".getBytes(StandardCharsets.UTF_8);

        exchange.sendResponseHeaders(status, resp.length);
        exchange.getResponseBody().write(resp);
        exchange.getResponseBody().close();
    }

    // -------------------------------------------------------------------------
    // Helper
    // -------------------------------------------------------------------------

    private String hmac(String payload) throws Exception {
        Mac mac = Mac.getInstance(HMAC_ALGORITHM);
        mac.init(new SecretKeySpec(SECRET.getBytes(StandardCharsets.UTF_8), HMAC_ALGORITHM));
        return HexFormat.of().formatHex(mac.doFinal(payload.getBytes(StandardCharsets.UTF_8)));
    }

    private WebhookPushNotifier notifier() {
        return WebhookPushNotifier.builder()
            .url(baseUrl + "/hook")
            .timeout(Duration.ofSeconds(5))
            .maxRetries(0)
            .build();
    }

    private WebhookPushNotifier notifierWithSecret() {
        return WebhookPushNotifier.builder()
            .url(baseUrl + "/hook")
            .secret(SECRET)
            .timeout(Duration.ofSeconds(5))
            .maxRetries(0)
            .build();
    }

    // -------------------------------------------------------------------------
    // Tests: request format
    // -------------------------------------------------------------------------

    @Test
    void sendsPostRequest() throws Exception {
        notifier().notify(Map.of("skill", "echo"));
        assertThat(requestLatch.await(3, TimeUnit.SECONDS)).isTrue();
        assertThat(lastMethod.get()).isEqualTo("POST");
    }

    @Test
    void sendsJsonContentTypeHeader() throws Exception {
        notifier().notify(Map.of("skill", "echo"));
        assertThat(requestLatch.await(3, TimeUnit.SECONDS)).isTrue();
        assertThat(lastContentType.get()).isEqualTo("application/json");
    }

    @Test
    void bodyIsValidJson() throws Exception {
        notifier().notify(Map.of("skill", "echo", "result", "hello"));
        assertThat(requestLatch.await(3, TimeUnit.SECONDS)).isTrue();

        var parsed = MAPPER.readTree(lastBody.get());
        assertThat(parsed.has("skill")).isTrue();
        assertThat(parsed.get("skill").asText()).isEqualTo("echo");
    }

    // -------------------------------------------------------------------------
    // Tests: HMAC signature
    // -------------------------------------------------------------------------

    @Test
    void signatureHeaderAbsentWhenNoSecret() throws Exception {
        notifier().notify(Map.of("skill", "echo"));
        assertThat(requestLatch.await(3, TimeUnit.SECONDS)).isTrue();
        assertThat(lastSignatureHeader.get()).isNull();
    }

    @Test
    void signatureHeaderPresentWhenSecretConfigured() throws Exception {
        notifierWithSecret().notify(Map.of("skill", "echo"));
        assertThat(requestLatch.await(3, TimeUnit.SECONDS)).isTrue();
        assertThat(lastSignatureHeader.get()).isNotNull();
        assertThat(lastSignatureHeader.get()).startsWith("sha256=");
    }

    @Test
    void signatureIsCryptographicallyValid() throws Exception {
        notifierWithSecret().notify(Map.of("skill", "echo", "result", "hello"));
        assertThat(requestLatch.await(3, TimeUnit.SECONDS)).isTrue();

        String body = lastBody.get();
        String expectedSig = "sha256=" + hmac(body);
        assertThat(lastSignatureHeader.get()).isEqualTo(expectedSig);
    }

    // -------------------------------------------------------------------------
    // Tests: HTTP status handling
    // -------------------------------------------------------------------------

    @Test
    void succeedsOn200() {
        responseStatus.set(200);
        assertThatCode(() -> notifier().notify(Map.of("skill", "echo")))
            .doesNotThrowAnyException();
    }

    @Test
    void succeedsOn201() {
        responseStatus.set(201);
        assertThatCode(() -> notifier().notify(Map.of("skill", "echo")))
            .doesNotThrowAnyException();
    }

    @Test
    void throwsOn4xx() {
        responseStatus.set(400);
        assertThatThrownBy(() -> notifier().notify(Map.of("skill", "echo")))
            .isInstanceOf(PushNotifierException.class)
            .hasMessageContaining("400");
    }

    @Test
    void throwsAfterRetriesExhaustedOn5xx() throws Exception {
        responseStatus.set(500);
        requestLatch = new CountDownLatch(4); // maxRetries=3 means 4 attempts total

        var n = WebhookPushNotifier.builder()
            .url(baseUrl + "/hook")
            .timeout(Duration.ofSeconds(2))
            .maxRetries(3)
            .build();

        assertThatThrownBy(() -> n.notify(Map.of("skill", "echo")))
            .isInstanceOf(PushNotifierException.class)
            .hasMessageContaining("4 attempt");

        assertThat(requestLatch.await(30, TimeUnit.SECONDS)).isTrue();
        assertThat(requestCount.get()).isEqualTo(4);
    }

    // -------------------------------------------------------------------------
    // Tests: builder pattern
    // -------------------------------------------------------------------------

    @Test
    void builderSetsUrl() {
        var n = WebhookPushNotifier.builder()
            .url("http://example.com/hook")
            .build();
        assertThat(n.getUrl()).isEqualTo("http://example.com/hook");
    }

    @Test
    void builderSetsSecret() {
        var n = WebhookPushNotifier.builder()
            .url("http://example.com/hook")
            .secret("my-secret")
            .build();
        assertThat(n.getSecret()).isEqualTo("my-secret");
    }

    @Test
    void builderSetsMaxRetries() {
        var n = WebhookPushNotifier.builder()
            .url("http://example.com/hook")
            .maxRetries(5)
            .build();
        assertThat(n.getMaxRetries()).isEqualTo(5);
    }

    @Test
    void builderSetsTimeout() {
        var n = WebhookPushNotifier.builder()
            .url("http://example.com/hook")
            .timeout(Duration.ofSeconds(10))
            .build();
        assertThat(n.getTimeout()).isEqualTo(Duration.ofSeconds(10));
    }

    // -------------------------------------------------------------------------
    // Tests: convenience constructors
    // -------------------------------------------------------------------------

    @Test
    void convenienceConstructorNoSecret() {
        var n = new WebhookPushNotifier("http://example.com/hook");
        assertThat(n.getUrl()).isEqualTo("http://example.com/hook");
        assertThat(n.getSecret()).isNull();
    }

    @Test
    void convenienceConstructorWithSecret() {
        var n = new WebhookPushNotifier("http://example.com/hook", "s3cr3t");
        assertThat(n.getUrl()).isEqualTo("http://example.com/hook");
        assertThat(n.getSecret()).isEqualTo("s3cr3t");
    }

    @Test
    void convenienceConstructorSendsRequestSuccessfully() throws Exception {
        var n = new WebhookPushNotifier(baseUrl + "/hook");
        assertThatCode(() -> n.notify(Map.of("skill", "ping"))).doesNotThrowAnyException();
        assertThat(requestLatch.await(3, TimeUnit.SECONDS)).isTrue();
    }

    @Test
    void convenienceConstructorWithSecretSignsRequest() throws Exception {
        var n = new WebhookPushNotifier(baseUrl + "/hook", SECRET);
        n.notify(Map.of("skill", "ping"));
        assertThat(requestLatch.await(3, TimeUnit.SECONDS)).isTrue();

        assertThat(lastSignatureHeader.get()).startsWith("sha256=");
        String expectedSig = "sha256=" + hmac(lastBody.get());
        assertThat(lastSignatureHeader.get()).isEqualTo(expectedSig);
    }
}
