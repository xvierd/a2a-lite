package com.a2alite.push;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.InvalidKeyException;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Map;
import java.util.Objects;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * A {@link PushNotifier} that POSTs events to an HTTP webhook endpoint.
 *
 * <p>Features:
 * <ul>
 *   <li>JSON body serialization via Jackson</li>
 *   <li>Optional HMAC-SHA256 signature in the {@code X-A2A-Signature: sha256=&lt;hex&gt;} header</li>
 *   <li>Configurable retries with exponential back-off on 5xx responses</li>
 * </ul>
 *
 * <pre>{@code
 * // Simple — no signing
 * var notifier = new WebhookPushNotifier("https://example.com/hook");
 *
 * // With HMAC signing
 * var notifier = new WebhookPushNotifier("https://example.com/hook", "my-secret");
 *
 * // Full builder
 * var notifier = WebhookPushNotifier.builder()
 *     .url("https://example.com/hook")
 *     .secret("my-secret")
 *     .maxRetries(5)
 *     .timeout(Duration.ofSeconds(10))
 *     .build();
 * }</pre>
 */
public class WebhookPushNotifier implements PushNotifier {

    private static final Logger LOGGER = Logger.getLogger(WebhookPushNotifier.class.getName());
    private static final String HMAC_ALGORITHM = "HmacSHA256";
    private static final String SIGNATURE_HEADER = "X-A2A-Signature";

    private final String url;
    private final String secret;
    private final int maxRetries;
    private final Duration timeout;
    private final HttpClient httpClient;
    private final ObjectMapper mapper;

    // -------------------------------------------------------------------------
    // Constructors
    // -------------------------------------------------------------------------

    /**
     * Create a notifier that POSTs to the given URL without signing.
     *
     * @param url the webhook endpoint URL
     */
    public WebhookPushNotifier(String url) {
        this(url, null);
    }

    /**
     * Create a notifier that POSTs to the given URL with HMAC-SHA256 signing.
     *
     * @param url    the webhook endpoint URL
     * @param secret the signing secret; {@code null} disables signing
     */
    public WebhookPushNotifier(String url, String secret) {
        this(builder().url(url).secret(secret));
    }

    private WebhookPushNotifier(Builder builder) {
        this.url = Objects.requireNonNull(builder.url, "url is required");
        this.secret = builder.secret;
        this.maxRetries = builder.maxRetries;
        this.timeout = builder.timeout;
        this.httpClient = builder.httpClient != null ? builder.httpClient
            : HttpClient.newBuilder()
                .connectTimeout(timeout)
                .build();
        this.mapper = new ObjectMapper();
    }

    // -------------------------------------------------------------------------
    // PushNotifier
    // -------------------------------------------------------------------------

    @Override
    public void notify(Map<String, Object> event) {
        String body;
        try {
            body = mapper.writeValueAsString(event);
        } catch (JsonProcessingException e) {
            throw new PushNotifierException("Failed to serialize event to JSON", e);
        }

        Exception lastException = null;
        for (int attempt = 0; attempt <= maxRetries; attempt++) {
            if (attempt > 0) {
                final long delayMs = (long) (Math.pow(2, attempt - 1) * 500);
                final int currentAttempt = attempt;
                LOGGER.fine(() -> "Webhook retry " + currentAttempt + "/" + maxRetries + " after " + delayMs + "ms");
                try {
                    Thread.sleep(delayMs);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    throw new PushNotifierException("Interrupted during retry back-off", ie);
                }
            }

            try {
                var requestBuilder = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(timeout)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8));

                if (secret != null && !secret.isEmpty()) {
                    String signature = computeSignature(body);
                    requestBuilder.header(SIGNATURE_HEADER, "sha256=" + signature);
                }

                var response = httpClient.send(requestBuilder.build(),
                    HttpResponse.BodyHandlers.ofString());

                int status = response.statusCode();
                if (status >= 200 && status < 300) {
                    LOGGER.fine(() -> "Webhook delivered to " + url + " — HTTP " + status);
                    return;
                }

                if (status >= 500) {
                    lastException = new PushNotifierException(
                        "Webhook server error: HTTP " + status + " from " + url);
                    LOGGER.log(Level.WARNING, "Webhook failed with HTTP {0} (attempt {1}/{2})",
                        new Object[]{status, attempt + 1, maxRetries + 1});
                    continue; // retry
                }

                // 4xx — do not retry
                throw new PushNotifierException("Webhook client error: HTTP " + status + " from " + url);

            } catch (PushNotifierException e) {
                throw e;
            } catch (Exception e) {
                lastException = new PushNotifierException("Webhook delivery failed: " + e.getMessage(), e);
                LOGGER.log(Level.WARNING, "Webhook attempt " + (attempt + 1) + " failed", e);
            }
        }

        throw new PushNotifierException(
            "Webhook delivery failed after " + (maxRetries + 1) + " attempt(s)", lastException);
    }

    // -------------------------------------------------------------------------
    // Internal helpers
    // -------------------------------------------------------------------------

    private String computeSignature(String payload) {
        try {
            Mac mac = Mac.getInstance(HMAC_ALGORITHM);
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), HMAC_ALGORITHM));
            byte[] digest = mac.doFinal(payload.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException | InvalidKeyException e) {
            throw new PushNotifierException("Failed to compute HMAC-SHA256 signature", e);
        }
    }

    // -------------------------------------------------------------------------
    // Accessors (useful for testing)
    // -------------------------------------------------------------------------

    public String getUrl() { return url; }
    public String getSecret() { return secret; }
    public int getMaxRetries() { return maxRetries; }
    public Duration getTimeout() { return timeout; }

    // -------------------------------------------------------------------------
    // Builder
    // -------------------------------------------------------------------------

    public static Builder builder() {
        return new Builder();
    }

    public static final class Builder {
        private String url;
        private String secret;
        private int maxRetries = 3;
        private Duration timeout = Duration.ofSeconds(5);
        private HttpClient httpClient;

        private Builder() {}

        public Builder url(String url) {
            this.url = url;
            return this;
        }

        public Builder secret(String secret) {
            this.secret = secret;
            return this;
        }

        public Builder maxRetries(int maxRetries) {
            this.maxRetries = maxRetries;
            return this;
        }

        public Builder timeout(Duration timeout) {
            this.timeout = Objects.requireNonNull(timeout);
            return this;
        }

        /** Override the HTTP client (useful for testing). */
        public Builder httpClient(HttpClient httpClient) {
            this.httpClient = httpClient;
            return this;
        }

        public WebhookPushNotifier build() {
            return new WebhookPushNotifier(this);
        }
    }
}
