package com.a2alite.push;

import com.fasterxml.jackson.databind.ObjectMapper;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Sends skill completion events as HTTP POST requests to a webhook URL.
 *
 * <p>Features:
 * <ul>
 * <li>Automatic retry with exponential backoff</li>
 * <li>Optional HMAC-SHA256 request signing via {@code X-A2A-Signature} header</li>
 * <li>Configurable headers, retries, and timeout</li>
 * </ul>
 *
 * <p>Example:
 * <pre>{@code
 * PushNotifier notifier = WebhookPushNotifier.builder()
 *     .url("https://api.example.com/a2a-events")
 *     .secret("my-webhook-secret")
 *     .maxRetries(3)
 *     .build();
 *
 * Agent agent = Agent.builder()
 *     .name("Bot")
 *     .description("...")
 *     .pushNotifier(notifier)
 *     .build();
 * }</pre>
 */
public class WebhookPushNotifier implements PushNotifier {

    private static final Logger logger = Logger.getLogger(WebhookPushNotifier.class.getName());
    private static final ObjectMapper objectMapper = new ObjectMapper();

    private final String url;
    private final String secret;
    private final Map<String, String> headers;
    private final int maxRetries;
    private final Duration timeout;
    private final HttpClient httpClient;

    private WebhookPushNotifier(Builder builder) {
        this.url = builder.url;
        this.secret = builder.secret;
        this.headers = builder.headers != null ? Map.copyOf(builder.headers) : Map.of();
        this.maxRetries = builder.maxRetries;
        this.timeout = builder.timeout;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(timeout)
                .build();
    }

    /**
     * Convenience constructor for simple webhook without signing.
     *
     * @param url the webhook endpoint URL
     */
    public WebhookPushNotifier(String url) {
        this(builder().url(url));
    }

    /**
     * Convenience constructor with HMAC signing.
     *
     * @param url    the webhook endpoint URL
     * @param secret the HMAC-SHA256 signing secret
     */
    public WebhookPushNotifier(String url, String secret) {
        this(builder().url(url).secret(secret));
    }

    /** Returns the webhook URL. */
    public String getUrl() {
        return url;
    }

    /** Returns the HMAC signing secret, or {@code null} if not configured. */
    public String getSecret() {
        return secret;
    }

    /** Returns the maximum number of delivery attempts. */
    public int getMaxRetries() {
        return maxRetries;
    }

    /** Returns the per-request timeout. */
    public Duration getTimeout() {
        return timeout;
    }

    /**
     * Sends the event to the webhook. Retries up to {@code maxRetries} times on
     * transient failures. {@code maxRetries=0} means one attempt, no retries.
     *
     * @throws PushNotifierException if all attempts fail
     */
    @Override
    public void notify(Map<String, Object> event) {
        String payload;
        try {
            payload = objectMapper.writeValueAsString(event);
        } catch (Exception e) {
            throw new PushNotifierException("Failed to serialize push notification event", e);
        }

        Exception lastError = null;
        int totalAttempts = maxRetries + 1; // maxRetries=0 → 1 attempt, maxRetries=3 → 4 attempts

        for (int attempt = 0; attempt < totalAttempts; attempt++) {
            try {
                HttpRequest.Builder requestBuilder = HttpRequest.newBuilder()
                        .uri(URI.create(url))
                        .timeout(timeout)
                        .header("Content-Type", "application/json")
                        .header("X-A2A-Event", String.valueOf(event.get("skill")));

                // Apply custom headers
                headers.forEach(requestBuilder::header);

                // Apply HMAC signature if secret configured
                if (secret != null && !secret.isEmpty()) {
                    requestBuilder.header("X-A2A-Signature", "sha256=" + sign(payload));
                }

                HttpRequest request = requestBuilder
                        .POST(HttpRequest.BodyPublishers.ofString(payload, StandardCharsets.UTF_8))
                        .build();

                HttpResponse<String> response = httpClient.send(
                        request,
                        HttpResponse.BodyHandlers.ofString()
                );

                int status = response.statusCode();
                if (status >= 200 && status < 300) {
                    logger.fine("Push notification sent: skill=" + event.get("skill")
                            + " status=" + status);
                    return; // success
                }

                lastError = new PushNotifierException("Webhook responded with HTTP " + status);

            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new PushNotifierException("Push notification interrupted", e);
            } catch (PushNotifierException e) {
                throw e; // don't wrap
            } catch (Exception e) {
                lastError = e;
            }

            if (attempt < totalAttempts - 1) {
                long waitMs = (long) (1000 * Math.pow(2, attempt)); // 1s, 2s, 4s
                logger.warning("Push notification failed (attempt " + (attempt + 1) + "/"
                        + totalAttempts + "), retrying in " + waitMs + "ms: " + lastError);
                try {
                    Thread.sleep(waitMs);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    throw new PushNotifierException("Push notification interrupted during retry", ie);
                }
            }
        }

        String reason = lastError != null ? lastError.getMessage() : "unknown error";
        throw new PushNotifierException("Push notification failed after " + totalAttempts + " attempt(s): " + reason, lastError);
    }

    private String sign(String payload) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            byte[] hmacBytes = mac.doFinal(payload.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hmacBytes);
        } catch (Exception e) {
            throw new RuntimeException("Failed to sign payload", e);
        }
    }

    /** @return a new Builder for WebhookPushNotifier */
    public static Builder builder() {
        return new Builder();
    }

    public static final class Builder {
        private String url;
        private String secret;
        private Map<String, String> headers;
        private int maxRetries = 3;
        private Duration timeout = Duration.ofSeconds(10);

        private Builder() {}

        public Builder url(String url) {
            this.url = url;
            return this;
        }

        public Builder secret(String secret) {
            this.secret = secret;
            return this;
        }

        public Builder headers(Map<String, String> headers) {
            this.headers = headers;
            return this;
        }

        public Builder maxRetries(int maxRetries) {
            this.maxRetries = maxRetries;
            return this;
        }

        public Builder timeout(Duration timeout) {
            this.timeout = timeout;
            return this;
        }

        public WebhookPushNotifier build() {
            if (url == null || url.isBlank()) {
                throw new IllegalArgumentException("url is required");
            }
            return new WebhookPushNotifier(this);
        }
    }
}
