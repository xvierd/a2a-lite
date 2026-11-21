import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.a2aproject.sdk.A2A;
import org.a2aproject.sdk.client.Client;
import org.a2aproject.sdk.client.ClientEvent;
import org.a2aproject.sdk.client.MessageEvent;
import org.a2aproject.sdk.client.TaskEvent;
import org.a2aproject.sdk.client.TaskUpdateEvent;
import org.a2aproject.sdk.client.config.ClientConfig;
import org.a2aproject.sdk.client.http.A2ACardResolver;
import org.a2aproject.sdk.client.transport.jsonrpc.JSONRPCTransport;
import org.a2aproject.sdk.client.transport.jsonrpc.JSONRPCTransportConfig;
import org.a2aproject.sdk.client.transport.rest.RestTransport;
import org.a2aproject.sdk.client.transport.rest.RestTransportConfig;
import org.a2aproject.sdk.client.transport.spi.interceptors.ClientCallContext;
import org.a2aproject.sdk.spec.A2AClientException;
import org.a2aproject.sdk.spec.AgentCard;
import org.a2aproject.sdk.spec.Message;
import org.a2aproject.sdk.spec.TaskNotFoundError;
import org.a2aproject.sdk.spec.TaskQueryParams;
import org.a2aproject.sdk.spec.TaskState;
import org.a2aproject.sdk.spec.TaskStatusUpdateEvent;
import org.a2aproject.sdk.spec.TextPart;

/** Independent consumer: only official SDK classes are on the runtime classpath. */
public final class OfficialProbe {
    private static final ClientCallContext CONTEXT = new ClientCallContext(Map.of(),
            Map.of("X-API-Key", "interop-secret", "A2A-Version", "1.0"));

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private static Client client(AgentCard card, String binding, boolean streaming) throws Exception {
        var builder = Client.builder(card).clientConfig(ClientConfig.builder().setStreaming(streaming).build());
        return switch (binding) {
            case "JSONRPC" -> builder.withTransport(JSONRPCTransport.class, new JSONRPCTransportConfig()).build();
            case "HTTP+JSON" -> builder.withTransport(RestTransport.class, new RestTransportConfig()).build();
            default -> throw new IllegalArgumentException("Unknown binding: " + binding);
        };
    }

    private static List<String> texts(Message message) {
        return message.parts().stream().filter(TextPart.class::isInstance)
                .map(TextPart.class::cast).map(TextPart::text).toList();
    }

    private static ClientEvent send(Client client, String json) throws Exception {
        var events = new ArrayList<ClientEvent>();
        client.sendMessage(A2A.toUserMessage(json), List.of((event, card) -> events.add(event)), null, CONTEXT);
        require(events.size() == 1, "Expected one unary event for " + json + ", got " + events);
        return events.get(0);
    }

    private static void checkUnary(Client client) throws Exception {
        var greeting = send(client, "{\"skill\":\"greet\",\"params\":{\"text\":\"hello\"}}");
        require(greeting instanceof MessageEvent msg && texts(msg.getMessage()).equals(List.of("hello")),
                "greet did not return a hello Message: " + greeting);

        var response = send(client, "{\"skill\":\"taskProbe\",\"params\":{}}");
        require(response instanceof TaskEvent, "taskProbe did not return a Task: " + response);
        var task = ((TaskEvent) response).getTask();
        require(!task.id().isBlank() && task.status().state() == TaskState.TASK_STATE_COMPLETED,
                "taskProbe returned an incomplete Task: " + task);
        boolean idInMessage = task.status().message() != null
                && texts(task.status().message()).equals(List.of(task.id()));
        boolean idInArtifact = task.artifacts() != null && task.artifacts().stream()
                .flatMap(artifact -> artifact.parts().stream())
                .anyMatch(part -> part instanceof TextPart text && text.text().equals(task.id()));
        require(idInMessage || idInArtifact, "taskProbe result did not contain its own task ID: " + task);
        var read = client.getTask(new TaskQueryParams(task.id()), CONTEXT);
        require(read.id().equals(task.id()) && read.status().state() == TaskState.TASK_STATE_COMPLETED,
                "GetTask returned the wrong Task: " + read);
        try {
            client.getTask(new TaskQueryParams(UUID.randomUUID().toString()), CONTEXT);
            throw new AssertionError("GetTask accepted a missing task");
        } catch (A2AClientException e) {
            if (!(e.getCause() instanceof TaskNotFoundError)) {
                throw new AssertionError("Expected TaskNotFoundError for missing task", e);
            }
        }
    }

    private static void checkStream(Client client, String skill, TaskState expectedState) throws Exception {
        var done = new CompletableFuture<Void>();
        var events = new ArrayList<ClientEvent>();
        var message = A2A.toUserMessage("{\"skill\":\"" + skill + "\",\"params\":{}}");
        client.sendMessage(message, List.of((event, card) -> events.add(event)), error -> {
            // SDK 1.5.1 signals normal stream completion via a null error.
            if (error == null) done.complete(null);
            else done.completeExceptionally(error);
        }, CONTEXT);
        done.get(20, TimeUnit.SECONDS);
        require(!events.isEmpty() && events.get(0) instanceof TaskEvent, skill + ": missing initial Task");
        String taskId = ((TaskEvent) events.get(0)).getTask().id();
        var chunks = new ArrayList<String>();
        TaskState lastState = null;
        for (ClientEvent event : events.subList(1, events.size())) {
            require(event instanceof TaskUpdateEvent update && update.getUpdateEvent() instanceof TaskStatusUpdateEvent,
                    skill + ": unexpected fixture event " + event);
            var status = (TaskStatusUpdateEvent) ((TaskUpdateEvent) event).getUpdateEvent();
            require(taskId.equals(status.taskId()), skill + ": stream changed task ID");
            require(lastState == null || !lastState.isFinal(), skill + ": update after terminal state");
            lastState = status.status().state();
            if (lastState == TaskState.TASK_STATE_WORKING && status.status().message() != null) {
                chunks.addAll(texts(status.status().message()));
            }
        }
        require(lastState == expectedState, skill + ": expected " + expectedState + ", got " + lastState);
        if (skill.equals("stream")) {
            require(chunks.equals(List.of("one", "two", "three")), "Wrong stream chunks: " + chunks);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException("Usage: official-java URL BINDING");
        var properties = new Properties();
        try (var in = Client.class.getResourceAsStream(
                "/META-INF/maven/org.a2aproject.sdk/a2a-java-sdk-client/pom.properties")) {
            properties.load(in);
        }
        String version = properties.getProperty("version");
        require("1.5.1.Final".equals(version), "Unexpected official Java SDK version: " + version);
        AgentCard card = A2ACardResolver.builder().baseUrl(args[0]).build().getAgentCard();
        require(card.capabilities().streaming(), "Fixture must advertise streaming");
        String binding = args[1];
        try (Client unary = client(card, binding, false); Client streaming = client(card, binding, true)) {
            checkUnary(unary);
            checkStream(streaming, "stream", TaskState.TASK_STATE_COMPLETED);
            checkStream(streaming, "fail", TaskState.TASK_STATE_FAILED);
        }
        System.out.printf("A2A_LITE_OFFICIAL {\"sdk\":\"a2a-java-sdk-client\",\"sdkVersion\":\"%s\","
                + "\"binding\":\"%s\",\"message\":true,\"task\":true,\"taskRead\":true,\"taskNotFound\":true,"
                + "\"stream\":true,\"failure\":true}%n",
                version, binding);
    }
}
