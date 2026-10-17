package com.a2alite;

import com.a2alite.streaming.StreamingHandler;
import com.a2alite.streaming.StreamingHandler.StreamResult;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

import static org.assertj.core.api.Assertions.assertThat;

class StreamingTest {

    @Test
    void shouldStreamChunks() {
        StreamResult result = StreamingHandler.stream(sink -> {
            sink.accept("Hello ");
            sink.accept("World");
        });

        var chunks = new ArrayList<>();
        result.forEach(chunks::add);
        assertThat(chunks).containsExactly("Hello ", "World");
    }

    @Test
    void shouldCollectStream() {
        StreamResult result = StreamingHandler.stream(sink -> {
            sink.accept("Hello ");
            sink.accept("World");
        });

        assertThat(StreamingHandler.collect(result)).isEqualTo("Hello World");
    }

    @Test
    void shouldStreamFromIterator() {
        var list = List.of("a", "b", "c");
        StreamResult result = StreamingHandler.fromIterator(list.iterator());

        var chunks = new ArrayList<>();
        result.forEach(chunks::add);
        assertThat(chunks).containsExactly("a", "b", "c");
    }

    @Test
    void shouldStreamFromJavaStream() {
        StreamResult result = StreamingHandler.fromStream(Stream.of(1, 2, 3));

        var chunks = new ArrayList<>();
        result.forEach(chunks::add);
        assertThat(chunks).containsExactly(1, 2, 3);
    }

    @Test
    void shouldDetectStreamingResult() {
        StreamResult result = StreamingHandler.stream(sink -> sink.accept("test"));
        assertThat(StreamingHandler.isStreaming(result)).isTrue();
        assertThat(StreamingHandler.isStreaming("not streaming")).isFalse();
    }

    @Test
    void shouldHandleEmptyStream() {
        StreamResult result = StreamingHandler.stream(sink -> {
            // empty
        });

        var chunks = new ArrayList<>();
        result.forEach(chunks::add);
        assertThat(chunks).isEmpty();
    }

    @Test
    void shouldHandleLargeStream() {
        StreamResult result = StreamingHandler.stream(sink -> {
            for (int i = 0; i < 1000; i++) {
                sink.accept("chunk-" + i);
            }
        });

        var chunks = new ArrayList<>();
        result.forEach(chunks::add);
        assertThat(chunks).hasSize(1000);
    }

    @Test
    void shouldStreamMixedTypes() {
        StreamResult result = StreamingHandler.stream(sink -> {
            sink.accept("text");
            sink.accept(42);
            sink.accept(List.of("a", "b"));
        });

        var chunks = new ArrayList<>();
        result.forEach(chunks::add);
        assertThat(chunks).hasSize(3);
        assertThat(chunks.get(0)).isEqualTo("text");
        assertThat(chunks.get(1)).isEqualTo(42);
    }

    @Test
    void shouldBeMarkedAsStreaming() {
        StreamResult result = StreamingHandler.stream(sink -> {});
        assertThat(result.isStreaming()).isTrue();
    }

    @Test
    void shouldStreamFromEmptyIterator() {
        StreamResult result = StreamingHandler.fromIterator(List.of().iterator());
        var chunks = new ArrayList<>();
        result.forEach(chunks::add);
        assertThat(chunks).isEmpty();
    }

    @Test
    void shouldStreamSingleChunk() {
        StreamResult result = StreamingHandler.stream(sink -> sink.accept("only one"));
        assertThat(StreamingHandler.collect(result)).isEqualTo("only one");
    }

    @Test
    void shouldCollectFromIteratorStream() {
        StreamResult result = StreamingHandler.fromIterator(List.of("a", "b").iterator());
        assertThat(StreamingHandler.collect(result)).isEqualTo("ab");
    }
    @Test
    void closingBeforeIterationDoesNotStartProducer() {
        var calls = new java.util.concurrent.atomic.AtomicInteger();
        var result = StreamingHandler.stream(sink -> calls.incrementAndGet());
        result.close();
        assertThat(result.iterator().hasNext()).isFalse();
        assertThat(calls).hasValue(0);
    }

    @Test
    void closingStopsBlockedProducer() throws Exception {
        var stopped = new java.util.concurrent.CountDownLatch(1);
        var result = StreamingHandler.stream(sink -> {
            try {
                while (true) sink.accept("chunk");
            } finally { stopped.countDown(); }
        });
        assertThat(result.iterator().next()).isEqualTo("chunk");
        result.close();
        assertThat(stopped.await(1, java.util.concurrent.TimeUnit.SECONDS)).isTrue();
    }

    @Test
    void collectClosesUnderlyingJavaStream() {
        var closed = new java.util.concurrent.atomic.AtomicBoolean();
        var result = StreamingHandler.fromStream(Stream.of("one").onClose(() -> closed.set(true)));
        assertThat(StreamingHandler.collect(result)).isEqualTo("one");
        assertThat(closed).isTrue();
    }

}
