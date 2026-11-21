package com.a2alite;

import com.a2alite.errors.RemoteAgentException;
import com.a2alite.streaming.StreamingHandler;
import org.a2aproject.sdk.client.http.ServerSentEventParser;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Set;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;

/** A single-pass stream of complete A2A StreamResponse objects. Close it when stopping early. */
public final class TaskEventStream implements Iterable<Map<String, Object>>, AutoCloseable {
    private static final Set<String> END_STATES = Set.of("TASK_STATE_COMPLETED", "TASK_STATE_FAILED",
        "TASK_STATE_REJECTED", "TASK_STATE_CANCELED");
    private static final Set<String> INTERRUPTED_STATES = Set.of("TASK_STATE_INPUT_REQUIRED", "TASK_STATE_AUTH_REQUIRED");
    private static final List<String> EVENT_TYPES = List.of("task", "message", "statusUpdate", "artifactUpdate");

    private final CompletableFuture<HttpResponse<InputStream>> response;
    private final String requestId;
    private final String taskId;
    private boolean iterated;
    private volatile boolean closed;

    TaskEventStream(CompletableFuture<HttpResponse<InputStream>> response, String requestId, String taskId) {
        this.response = response;
        this.requestId = requestId;
        this.taskId = taskId;
    }

    @Override
    public synchronized Iterator<Map<String, Object>> iterator() {
        if (iterated) throw new IllegalStateException("A remote stream can only be consumed once");
        iterated = true;
        return new EventIterator();
    }

    private final class EventIterator implements Iterator<Map<String, Object>> {
        private String frame;
        private final ServerSentEventParser parser = new ServerSentEventParser(
            event -> frame = event.data(),
            error -> { throw new RemoteAgentException("Invalid SSE event: " + error.getMessage()); });
        private BufferedReader reader;
        private boolean firstLine = true;
        private boolean firstEvent = true;
        private boolean ended;
        private boolean interruptedState;
        private Map<String, Object> buffered;

        @Override
        public boolean hasNext() {
            if (closed) return false;
            if (buffered != null) return true;
            if (ended) return false;
            try {
                if (reader == null) reader = open();
                var json = readFrame();
                if (json == null) {
                    close();
                    return false;
                }
                var event = ClientRpc.object(ClientRpc.result(json, requestId, 200), "stream event");
                String kind = null;
                for (var key : EVENT_TYPES) {
                    if (event.containsKey(key)) {
                        if (kind != null) throw new RemoteAgentException("Ambiguous A2A stream event", event);
                        kind = key;
                    }
                }
                if (kind == null) throw new RemoteAgentException("Unknown A2A stream event", event);
                var payload = ClientRpc.object(event.get(kind), kind);
                if (taskId != null) {
                    if (firstEvent && !kind.equals("task")) {
                        throw new RemoteAgentException("SubscribeToTask must begin with a Task snapshot", event);
                    }
                    if (kind.equals("message") || !taskId.equals(payload.get(kind.equals("task") ? "id" : "taskId"))) {
                        throw new RemoteAgentException("Stream event does not belong to the requested Task", event);
                    }
                }
                firstEvent = false;
                var state = payload.get("status") instanceof Map<?, ?> status ? status.get("state") : null;
                ended = kind.equals("message") || state instanceof String && END_STATES.contains(state);
                interruptedState = state instanceof String && INTERRUPTED_STATES.contains(state);
                if (ended) release();
                buffered = event;
                return !closed;
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                close();
                throw new CancellationException("Interrupted while waiting for the remote stream");
            } catch (IOException | ExecutionException | RuntimeException e) {
                if (closed) return false;
                close();
                if (e instanceof RuntimeException failure) throw failure;
                var failure = new RemoteAgentException("Remote stream failed: " + e.getMessage());
                failure.initCause(e);
                throw failure;
            }
        }

        private BufferedReader open() throws InterruptedException, ExecutionException, IOException {
            var http = response.get();
            int status = http.statusCode();
            var mime = http.headers().firstValue("Content-Type").orElse("").split(";", 2)[0].trim();
            if (status < 200 || status >= 300 || mime.equalsIgnoreCase("application/json")) {
                var body = new String(http.body().readAllBytes(), StandardCharsets.UTF_8);
                ClientRpc.result(body, requestId, status);
                throw new RemoteAgentException("Expected text/event-stream for streaming result");
            }
            if (!mime.equalsIgnoreCase("text/event-stream")) {
                throw new RemoteAgentException("Expected text/event-stream, received " + mime);
            }
            return new BufferedReader(new InputStreamReader(http.body(), StandardCharsets.UTF_8));
        }

        /** readLine accepts CR, LF and CRLF; only a blank line dispatches a complete event. */
        private String readFrame() throws IOException {
            frame = null;
            boolean partialEvent = false;
            String line;
            while ((line = reader.readLine()) != null) {
                if (firstLine) {
                    firstLine = false;
                    if (line.startsWith("\uFEFF")) line = line.substring(1);
                }
                if (line.isEmpty()) partialEvent = false;
                else if (!line.startsWith(":")) partialEvent = true;
                parser.processLine(line);
                if (frame != null) return frame;
            }
            if (interruptedState && !partialEvent) return null;
            throw new RemoteAgentException("Remote stream ended before a final message or task state");
        }

        @Override
        public Map<String, Object> next() {
            if (!hasNext()) throw new NoSuchElementException();
            var event = buffered;
            buffered = null;
            return event;
        }
    }

    StreamingHandler.StreamResult textChunks() {
        return new StreamingHandler.StreamResult() {
            @Override
            public Iterator<Object> iterator() {
                var events = TaskEventStream.this.iterator();
                return new Iterator<>() {
                    private Iterator<String> chunks = Collections.emptyIterator();

                    @Override
                    public boolean hasNext() {
                        while (!closed && !chunks.hasNext() && events.hasNext()) {
                            chunks = textParts(events.next()).iterator();
                        }
                        return !closed && chunks.hasNext();
                    }

                    @Override
                    public Object next() {
                        if (!hasNext()) throw new NoSuchElementException();
                        return chunks.next();
                    }
                };
            }

            @Override
            public void close() { TaskEventStream.this.close(); }
        };
    }

    private List<String> textParts(Map<String, Object> event) {
        Object content = event.get("message");
        if (event.get("artifactUpdate") instanceof Map<?, ?> update) content = update.get("artifact");
        if (event.getOrDefault("statusUpdate", event.get("task")) instanceof Map<?, ?> update
                && update.get("status") instanceof Map<?, ?> status) {
            if ("TASK_STATE_FAILED".equals(status.get("state"))) {
                close();
                throw new RemoteAgentException("Remote agent task failed", event);
            }
            content = status.get("message");
        }
        var chunks = new ArrayList<String>();
        if (content instanceof Map<?, ?> map && map.get("parts") instanceof List<?> parts) {
            for (var part : parts) {
                if (part instanceof Map<?, ?> item && item.get("text") instanceof String text) chunks.add(text);
            }
        }
        return chunks;
    }

    /** Cancel a pending request or close its active body, including a blocked read on another thread. */
    @Override
    public void close() {
        closed = true;
        release();
    }

    private void release() {
        response.thenAccept(http -> {
            try {
                http.body().close();
            } catch (IOException ignored) {
                // The HTTP exchange may have already closed.
            }
        });
        response.cancel(true);
    }
}
