package com.a2alite.push;

import org.apache.hc.client5.http.DnsResolver;
import org.apache.hc.client5.http.classic.methods.HttpPost;
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.http.ContentType;
import org.apache.hc.core5.http.io.entity.StringEntity;
import org.apache.hc.core5.util.Timeout;

import java.io.IOException;
import java.net.InetAddress;
import java.net.URI;
import java.net.UnknownHostException;
import java.util.Map;
import java.time.Duration;
import java.util.concurrent.*;
import org.apache.hc.core5.io.CloseMode;

/** Outbound transport for client-supplied task callbacks, never server-configured URLs. */
public final class PublicWebhookClient {
    @FunctionalInterface
    interface Resolver {
        InetAddress[] resolve(String host) throws UnknownHostException;
    }

    private static final ExecutorService DNS = new ThreadPoolExecutor(2, 2, 30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(32), runnable -> daemon(runnable, "a2a-callback-dns"), new ThreadPoolExecutor.AbortPolicy());
    private static final ScheduledThreadPoolExecutor DEADLINES = new ScheduledThreadPoolExecutor(1,
        runnable -> daemon(runnable, "a2a-callback-deadline"));
    static { DEADLINES.setRemoveOnCancelPolicy(true); }
    private final Resolver resolver;
    private final Duration deadline;

    private static Thread daemon(Runnable runnable, String name) {
        var thread = new Thread(runnable, name);
        thread.setDaemon(true);
        return thread;
    }

    public PublicWebhookClient() {
        this(InetAddress::getAllByName);
    }

    PublicWebhookClient(Resolver resolver) {
        this(resolver, Duration.ofSeconds(10));
    }

    PublicWebhookClient(Resolver resolver, Duration deadline) {
        this.resolver = resolver;
        this.deadline = deadline;
    }

    private InetAddress[] resolve(String host) throws UnknownHostException {
        Future<InetAddress[]> lookup;
        try {
            lookup = DNS.submit(() -> resolver.resolve(host));
        } catch (RejectedExecutionException e) {
            throw new IllegalArgumentException("Callback DNS capacity exhausted");
        }
        try {
            return lookup.get(Math.min(5000, deadline.toMillis()), TimeUnit.MILLISECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalArgumentException("Callback DNS interrupted", e);
        } catch (TimeoutException e) {
            throw new IllegalArgumentException("Callback DNS deadline exceeded", e);
        } catch (ExecutionException e) {
            throw new IllegalArgumentException("Callback DNS resolution failed", e.getCause());
        } finally { lookup.cancel(true); }
    }

    public void validate(String url) {
        resolveTarget(url);
    }

    private Target resolveTarget(String url) {
        try {
            URI uri = URI.create(url);
            if (!"https".equalsIgnoreCase(uri.getScheme())
                    || uri.getHost() == null || uri.getRawUserInfo() != null || uri.getRawFragment() != null
                    || uri.getPort() == 0 || uri.getPort() > 65535 || uri.getHost().contains("%")) {
                throw new IllegalArgumentException("Callback URL must be an HTTPS URL without credentials or fragments");
            }
            InetAddress[] addresses = resolve(uri.getHost());
            if (addresses.length == 0) {
                throw new IllegalArgumentException("Callback host did not resolve");
            }
            for (InetAddress address : addresses) {
                if (!isPublic(address)) {
                    throw new IllegalArgumentException("Callback host must resolve only to public addresses");
                }
            }
            return new Target(uri, addresses.clone());
        } catch (UnknownHostException e) {
            throw new IllegalArgumentException("Callback host could not be resolved", e);
        }
    }

    static boolean isPublic(InetAddress address) {
        if (address.isAnyLocalAddress() || address.isLoopbackAddress() || address.isLinkLocalAddress()
                || address.isSiteLocalAddress() || address.isMulticastAddress()) {
            return false;
        }
        byte[] bytes = address.getAddress();
        int a = bytes[0] & 255;
        int b = bytes[1] & 255;
        if (bytes.length == 4) {
            int c = bytes[2] & 255;
            return a != 0 && a < 224 && !(a == 100 && b >= 64 && b <= 127)
                && !(a == 192 && ((b == 0 && (c == 0 || c == 2)) || (b == 88 && c == 99)))
                && !(a == 198 && (b == 18 || b == 19 || (b == 51 && c == 100)))
                && !(a == 203 && b == 0 && c == 113);
        }
        // Global IPv6 unicast only; exclude documentation and transition mechanisms.
        return (a & 0xe0) == 0x20
            && !(a == 0x20 && b == 0x01 && (bytes[2] & 255) == 0x0d && (bytes[3] & 255) == 0xb8)
            && !(a == 0x20 && b == 0x02)
            && !(a == 0x20 && b == 0x01 && (bytes[2] & 255) < 2)
            && !(a == 0x3f && b == 0xff && (bytes[2] & 0xf0) == 0);
    }

    DnsResolver pinnedResolver(String url) {
        Target target = resolveTarget(url);
        return new DnsResolver() {
            @Override
            public InetAddress[] resolve(String host) throws UnknownHostException {
                if (!target.uri().getHost().equalsIgnoreCase(host)) {
                    throw new UnknownHostException("Unexpected callback host");
                }
                return target.addresses().clone();
            }

            @Override
            public String resolveCanonicalHostname(String host) throws UnknownHostException {
                resolve(host);
                return host;
            }
        };
    }

    public void post(String url, String json, Map<String, String> headers) throws IOException {
        // Resolve again immediately before delivery, and give the HTTP connector only
        // these validated addresses. The URL stays intact for Host, TLS verification/SNI.
        long expires = System.nanoTime() + deadline.toNanos();
        DnsResolver pinned = pinnedResolver(url);
        var manager = PoolingHttpClientConnectionManagerBuilder.create()
            .setDnsResolver(pinned)
            .setDefaultConnectionConfig(ConnectionConfig.custom()
                .setConnectTimeout(Timeout.ofSeconds(10)).setSocketTimeout(Timeout.ofSeconds(10)).build())
            .build();
        try (var client = HttpClients.custom().setConnectionManager(manager)
                .disableRedirectHandling().disableAutomaticRetries().disableCookieManagement()
                .setDefaultRequestConfig(RequestConfig.custom().setResponseTimeout(Timeout.ofSeconds(10)).build())
                .build()) {
            var request = new HttpPost(url);
            for (var header : headers.entrySet()) {
                if (header.getValue().contains("\r") || header.getValue().contains("\n")) {
                    throw new IllegalArgumentException("Invalid callback header");
                }
                request.setHeader(header.getKey(), header.getValue());
            }
            request.setEntity(new StringEntity(json, ContentType.create("application/a2a+json", java.nio.charset.StandardCharsets.UTF_8)));
            long remaining = expires - System.nanoTime();
            if (remaining <= 0) throw new IOException("Callback delivery deadline exceeded");
            var cancellation = DEADLINES.schedule(request::cancel, remaining, TimeUnit.NANOSECONDS);
            try {
                // Do not use the response-handler overload: it drains the response body,
                // letting an endless slow body extend delivery beyond the request timeout.
                var response = client.execute(request);
                try {
                    int status = response.getCode();
                    if (status < 200 || status >= 300) throw new IOException("Callback returned HTTP " + status);
                } finally { response.close(CloseMode.IMMEDIATE); }
            } finally { cancellation.cancel(false); }
        }
    }

    private record Target(URI uri, InetAddress[] addresses) {}
}
