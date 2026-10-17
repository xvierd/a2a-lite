package com.a2alite.push;

import org.junit.jupiter.api.Test;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.*;

class PublicWebhookClientTest {
    @Test
    void blocksNonPublicAddressesIncludingIpv4MappedIpv6() throws Exception {
        for (String address : List.of("127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254",
                "0.0.0.0", "100.64.0.1", "198.18.0.1", "192.0.2.1", "224.0.0.1", "255.255.255.255",
                "::1", "::", "fc00::1", "fe80::1", "2001:db8::1", "2002:7f00:1::1", "::ffff:127.0.0.1")) {
            assertThat(PublicWebhookClient.isPublic(InetAddress.getByName(address))).as(address).isFalse();
        }
        assertThat(PublicWebhookClient.isPublic(InetAddress.getByName("8.8.8.8"))).isTrue();
        assertThat(PublicWebhookClient.isPublic(InetAddress.getByName("2606:4700:4700::1111"))).isTrue();
    }

    @Test
    void rejectsMixedDnsAnswersAndMalformedUrls() throws Exception {
        var mixed = new PublicWebhookClient(host -> new InetAddress[] {
            InetAddress.getByName("8.8.8.8"), InetAddress.getByName("127.0.0.1") });
        assertThatThrownBy(() -> mixed.validate("https://callback.example/")).isInstanceOf(IllegalArgumentException.class);
        var publicOnly = new PublicWebhookClient(host -> new InetAddress[] { InetAddress.getByName("8.8.8.8") });
        for (String url : List.of("http://callback.example/", "file:///tmp/callback", "ftp://callback.example/", "https://user:pass@callback.example/",
                "https://callback.example/#fragment", "http://callback.example:0/", "http://callback.example:65536/")) {
            assertThatThrownBy(() -> publicOnly.validate(url)).as(url).isInstanceOf(IllegalArgumentException.class);
        }
    }

    @Test
    void pinsPublicDnsAnswerForDeliveryAndRevalidatesLaterDeliveries() throws Exception {
        var lookups = new AtomicInteger();
        var client = new PublicWebhookClient(host -> new InetAddress[] {
            InetAddress.getByName(lookups.incrementAndGet() == 1 ? "8.8.8.8" : "127.0.0.1") });
        var pinned = client.pinnedResolver("https://callback.example/events");
        assertThat(pinned.resolve("callback.example")[0].getHostAddress()).isEqualTo("8.8.8.8");
        assertThat(pinned.resolve("callback.example")[0].getHostAddress()).isEqualTo("8.8.8.8");
        assertThat(pinned.resolveCanonicalHostname("callback.example")).isEqualTo("callback.example");
        assertThat(lookups).hasValue(1);
        assertThatThrownBy(() -> pinned.resolve("another.example")).isInstanceOf(UnknownHostException.class);
        assertThatThrownBy(() -> client.post("https://callback.example/events", "{}", Map.of()))
            .isInstanceOf(IllegalArgumentException.class);
        assertThat(lookups).hasValue(2);
    }

    @Test
    void boundsDnsResolutionTime() {
        var interrupted = new java.util.concurrent.CountDownLatch(1);
        var client = new PublicWebhookClient(host -> {
            try { Thread.sleep(10_000); }
            catch (InterruptedException e) { interrupted.countDown(); Thread.currentThread().interrupt(); }
            return new InetAddress[] { InetAddress.getByName("8.8.8.8") };
        }, java.time.Duration.ofMillis(50));
        assertThatThrownBy(() -> client.validate("https://callback.example/"))
            .isInstanceOf(IllegalArgumentException.class).hasMessageContaining("deadline");
        try { assertThat(interrupted.await(1, java.util.concurrent.TimeUnit.SECONDS)).isTrue(); }
        catch (InterruptedException e) { throw new AssertionError(e); }
    }

    @Test
    void rejectedDestinationNeverReceivesHttpRequest() throws Exception {
        var calls = new AtomicInteger();
        var server = com.sun.net.httpserver.HttpServer.create(new java.net.InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> { calls.incrementAndGet(); exchange.sendResponseHeaders(204, -1); exchange.close(); });
        server.start();
        try {
            assertThatThrownBy(() -> new PublicWebhookClient().post("http://127.0.0.1:" + server.getAddress().getPort(), "{}", Map.of()))
                .isInstanceOf(IllegalArgumentException.class);
            assertThat(calls).hasValue(0);
        } finally { server.stop(0); }
    }
}
