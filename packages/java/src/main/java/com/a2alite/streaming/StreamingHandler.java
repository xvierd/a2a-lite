package com.a2alite.streaming;

import java.util.Iterator;
import java.util.function.Consumer;
import java.util.stream.Stream;

/**
 * Streaming support for A2A Lite agents.
 *
 * <p>Enables iterator-based streaming for LLM-style responses.
 *
 * <pre>{@code
 * agent.skill("chat", SkillConfig.withStreaming(), params -> {
 *     return StreamingHandler.stream(sink -> {
 *         for (String word : message.split(" ")) {
 *             sink.accept(word + " ");
 *         }
 *     });
 * });
 * }</pre>
 */
public class StreamingHandler {

    /**
     * A streaming result that can be iterated over.
     */
    public interface StreamResult extends Iterable<Object>, AutoCloseable {
        @Override
        default void close() {}

        /**
         * Check if this is a streaming result.
         */
        default boolean isStreaming() {
            return true;
        }
    }

    /**
     * Create a streaming result from a consumer that pushes chunks.
     *
     * @param producer A consumer that receives a sink to push chunks to
     * @return A StreamResult that can be iterated
     */
    public static StreamResult stream(Consumer<Consumer<Object>> producer) {
        return new StreamResult() {
            private boolean closed;
            private final java.util.List<ProducerIterator> iterators = new java.util.concurrent.CopyOnWriteArrayList<>();

            @Override
            public synchronized Iterator<Object> iterator() {
                var iterator = new ProducerIterator(producer);
                if (closed) iterator.close();
                iterators.add(iterator);
                return iterator;
            }

            @Override
            public synchronized void close() {
                closed = true;
                iterators.forEach(ProducerIterator::close);
            }
        };
    }

    private static final class ProducerIterator implements Iterator<Object> {
        private final java.util.concurrent.BlockingQueue<Object> queue = new java.util.concurrent.ArrayBlockingQueue<>(256);
        private final Consumer<Consumer<Object>> producer;
        private volatile boolean closed;
        private Thread thread;
        private Object next;

        ProducerIterator(Consumer<Consumer<Object>> producer) { this.producer = producer; }

        private synchronized void start() {
            if (thread != null || closed) return;
            thread = new Thread(() -> {
                try {
                    producer.accept(chunk -> {
                        if (closed) throw new java.util.concurrent.CancellationException();
                        put(chunk);
                    });
                    put(new Sentinel());
                } catch (Throwable error) {
                    if (!closed) put(new Failure(error));
                }
            }, "a2a-lite-stream");
            thread.setDaemon(true);
            thread.start();
        }

        private void put(Object value) {
            try {
                queue.put(value);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new java.util.concurrent.CancellationException();
            }
        }

        @Override
        public boolean hasNext() {
            if (closed) return false;
            start();
            try {
                if (next == null) next = queue.take();
                if (next instanceof Sentinel) {
                    close();
                    return false;
                }
                if (next instanceof Failure failure) {
                    close();
                    throw new IllegalStateException("Streaming producer failed", failure.cause());
                }
                return true;
            } catch (InterruptedException e) {
                close();
                Thread.currentThread().interrupt();
                return false;
            }
        }

        @Override
        public Object next() {
            if (!hasNext()) throw new java.util.NoSuchElementException();
            Object value = next;
            next = null;
            return value;
        }

        synchronized void close() {
            closed = true;
            if (thread != null) thread.interrupt();
            queue.clear();
            queue.offer(new Sentinel());
        }
    }

    private record Failure(Throwable cause) {}

    /**
     * Create a streaming result from an iterator.
     */
    public static StreamResult fromIterator(Iterator<?> iterator) {
        return () -> new Iterator<>() {
            @Override
            public boolean hasNext() {
                return iterator.hasNext();
            }

            @Override
            public Object next() {
                return iterator.next();
            }
        };
    }

    /**
     * Create a streaming result from a Java Stream.
     */
    public static StreamResult fromStream(Stream<?> stream) {
        var result = fromIterator(stream.iterator());
        return new StreamResult() {
            @Override
            public Iterator<Object> iterator() { return result.iterator(); }
            @Override
            public void close() { stream.close(); }
        };
    }

    /**
     * Check if a result is a streaming result.
     */
    public static boolean isStreaming(Object result) {
        return result instanceof StreamResult;
    }

    /**
     * Collect all chunks from a streaming result into a single string.
     */
    public static String collect(StreamResult result) {
        var sb = new StringBuilder();
        try (result) {
            for (var chunk : result) sb.append(chunk);
        }
        return sb.toString();
    }

    // Sentinel value to mark end of stream
    private static class Sentinel {}
}
