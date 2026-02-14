package com.a2alite.streaming;

import java.util.Iterator;
import java.util.Map;
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
    public interface StreamResult extends Iterable<Object> {
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
        return () -> new Iterator<>() {
            private final java.util.concurrent.LinkedBlockingQueue<Object> queue =
                new java.util.concurrent.LinkedBlockingQueue<>();
            private volatile boolean done = false;
            private Object next = null;
            private boolean started = false;

            private void ensureStarted() {
                if (!started) {
                    started = true;
                    new Thread(() -> {
                        try {
                            producer.accept(chunk -> {
                                try {
                                    queue.put(chunk);
                                } catch (InterruptedException e) {
                                    Thread.currentThread().interrupt();
                                }
                            });
                        } finally {
                            done = true;
                            try {
                                queue.put(new Sentinel());
                            } catch (InterruptedException e) {
                                Thread.currentThread().interrupt();
                            }
                        }
                    }).start();
                }
            }

            @Override
            public boolean hasNext() {
                ensureStarted();
                if (next != null) return true;
                try {
                    next = queue.take();
                    return !(next instanceof Sentinel);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return false;
                }
            }

            @Override
            public Object next() {
                if (next == null) {
                    if (!hasNext()) throw new java.util.NoSuchElementException();
                }
                Object result = next;
                next = null;
                return result;
            }
        };
    }

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
        return fromIterator(stream.iterator());
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
        for (var chunk : result) {
            sb.append(chunk);
        }
        return sb.toString();
    }

    // Sentinel value to mark end of stream
    private static class Sentinel {}
}
