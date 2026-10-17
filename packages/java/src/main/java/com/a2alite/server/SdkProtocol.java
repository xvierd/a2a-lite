package com.a2alite.server;

import com.a2alite.Agent;
import com.a2alite.push.PublicWebhookClient;
import com.fasterxml.jackson.databind.JsonNode;
import org.a2aproject.sdk.jsonrpc.common.json.JsonUtil;
import org.a2aproject.sdk.jsonrpc.common.wrappers.*;
import org.a2aproject.sdk.server.ServerCallContext;
import org.a2aproject.sdk.server.events.InMemoryQueueManager;
import org.a2aproject.sdk.server.events.MainEventBus;
import org.a2aproject.sdk.server.events.MainEventBusProcessor;
import org.a2aproject.sdk.server.extensions.A2AExtensions;
import org.a2aproject.sdk.server.requesthandlers.DefaultRequestHandler;
import org.a2aproject.sdk.server.tasks.InMemoryPushNotificationConfigStore;
import org.a2aproject.sdk.server.tasks.InMemoryTaskStore;
import org.a2aproject.sdk.server.tasks.PushNotificationSender;
import org.a2aproject.sdk.server.version.A2AVersionValidator;
import org.a2aproject.sdk.spec.*;

import java.util.HashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Flow;
import java.util.concurrent.atomic.AtomicReference;
import org.a2aproject.sdk.spec.InternalError;
import java.util.concurrent.Executors;
import java.util.logging.Level;
import java.util.logging.Logger;

/** Owns the SDK runtime. HTTP serialization and authentication stay in the adapter. */
final class SdkProtocol implements AutoCloseable {
    private static final Logger LOG = Logger.getLogger(SdkProtocol.class.getName());
    private final AgentCard card;
    private final DefaultRequestHandler handler;
    private final ValidatedPushStore configs;
    private final ExecutorService workers = Executors.newCachedThreadPool();
    private final ExecutorService consumers = Executors.newCachedThreadPool();
    private final ExecutorService pushes = Executors.newCachedThreadPool();
    private final ManagedProcessor processor;

    SdkProtocol(Agent agent, String host, int port) {
        card = agent.buildAgentCard(host, port);
        var ownership = new TaskOwnership();
        var tasks = new InMemoryTaskStore(ownership);
        var bus = new MainEventBus();
        var queues = new InMemoryQueueManager(tasks, bus);
        var callbacks = new PublicWebhookClient();
        configs = new ValidatedPushStore(callbacks);
        PushNotificationSender sender = (event, task) -> {
            if (task == null) return;
            for (var config : configs.getInfo(new ListTaskPushNotificationConfigsParams(task.id())).configs()) {
                try {
                    var headers = new HashMap<String, String>();
                    if (config.token() != null) headers.put("X-A2A-Notification-Token", config.token());
                    if (config.authentication() != null && config.authentication().credentials() != null) {
                        headers.put("Authorization", config.authentication().scheme() + " "
                            + config.authentication().credentials());
                    }
                    callbacks.post(config.url(), JsonUtil.toJsonStreamingEvent(event), headers);
                } catch (Exception e) {
                    // Do not put callback credentials or URLs into logs.
                    LOG.log(Level.WARNING, "Task callback delivery failed: " + e.getClass().getSimpleName());
                }
            }
        };
        processor = new ManagedProcessor(bus, tasks, sender, queues);
        processor.setPushNotificationExecutor(pushes);
        handler = DefaultRequestHandler.builder()
            .agentExecutor(agent.getExecutor()).taskStore(tasks).queueManager(queues)
            .pushConfigStore(configs).mainEventBusProcessor(processor)
            .executor(workers).eventConsumerExecutor(consumers)
            .authorizationProvider(ownership).pushNotificationsEnabled(true).build();
    }

    Object dispatch(String method, JsonNode params, Object id, ServerCallContext context) {
        A2AVersionValidator.validateProtocolVersion(card, context);
        A2AExtensions.validateRequiredExtensions(card, context);
        if (method.contains("PushNotificationConfig") && !context.getUser().isAuthenticated()) {
            throw new TaskNotFoundError();
        }
        return switch (method) {
            case "SendMessage" -> {
                var request = decode(params, MessageSendParams.class);
                validateEmbeddedPush(request, context);
                yield new SendMessageResponse(id, sendMessage(request, context));
            }
            case "SendStreamingMessage" -> {
                if (!Boolean.TRUE.equals(card.capabilities().streaming())) throw new UnsupportedOperationError();
                var request = decode(params, MessageSendParams.class);
                validateEmbeddedPush(request, context);
                yield handler.onMessageSendStream(request, context);
            }
            case "GetTask" -> new GetTaskResponse(id, handler.onGetTask(decode(params, TaskQueryParams.class), context));
            case "CancelTask" -> new CancelTaskResponse(id, handler.onCancelTask(decode(params, CancelTaskParams.class), context));
            case "ListTasks" -> new ListTasksResponse(id, handler.onListTasks(decode(params, ListTasksParams.class), context));
            case "SubscribeToTask" -> handler.onSubscribeToTask(decode(params, TaskIdParams.class), context);
            case "CreateTaskPushNotificationConfig" -> new CreateTaskPushNotificationConfigResponse(id,
                handler.onCreateTaskPushNotificationConfig(decode(params, TaskPushNotificationConfig.class), context));
            case "GetTaskPushNotificationConfig" -> new GetTaskPushNotificationConfigResponse(id,
                handler.onGetTaskPushNotificationConfig(decode(params, GetTaskPushNotificationConfigParams.class), context));
            case "ListTaskPushNotificationConfigs" -> new ListTaskPushNotificationConfigsResponse(id,
                handler.onListTaskPushNotificationConfigs(decode(params, ListTaskPushNotificationConfigsParams.class), context));
            case "DeleteTaskPushNotificationConfig" -> {
                handler.onDeleteTaskPushNotificationConfig(decode(params, DeleteTaskPushNotificationConfigParams.class), context);
                yield new DeleteTaskPushNotificationConfigResponse(id);
            }
            default -> throw new MethodNotFoundError();
        };
    }

    private EventKind sendMessage(MessageSendParams request, ServerCallContext context) {
        if (request.configuration() != null && Boolean.TRUE.equals(request.configuration().returnImmediately())) {
            return handler.onMessageSend(request, context);
        }
        // Aggregate the SDK stream for blocking requests. SDK 1.4's separate blocking
        // consumer can race queue closure and time out after a task already completed.
        var result = new CompletableFuture<EventKind>();
        var subscription = new AtomicReference<Flow.Subscription>();
        var taskId = new AtomicReference<String>();
        handler.onMessageSendStream(request, context).subscribe(new Flow.Subscriber<>() {
            @Override public void onSubscribe(Flow.Subscription value) {
                subscription.set(value);
                value.request(Long.MAX_VALUE);
            }
            @Override public void onNext(StreamingEventKind event) {
                try {
                    if (event instanceof Message message) {
                        result.complete(message);
                    } else if (event instanceof Task task) {
                        taskId.set(task.id());
                        if (task.status().state().isFinal() || task.status().state().isInterrupted()) result.complete(task);
                    } else if (event instanceof TaskStatusUpdateEvent update) {
                        taskId.set(update.taskId());
                        if (update.status().state().isFinal() || update.status().state().isInterrupted()) {
                            result.complete(handler.onGetTask(new TaskQueryParams(update.taskId(),
                                request.configuration() == null ? null : request.configuration().historyLength()), context));
                        }
                    }
                } catch (Throwable error) { result.completeExceptionally(error); }
            }
            @Override public void onError(Throwable error) { result.completeExceptionally(error); }
            @Override public void onComplete() {
                if (result.isDone()) return;
                try {
                    if (taskId.get() == null) throw new InternalError("Agent did not return a message or task");
                    result.complete(handler.onGetTask(new TaskQueryParams(taskId.get(),
                        request.configuration() == null ? null : request.configuration().historyLength()), context));
                } catch (Throwable error) { result.completeExceptionally(error); }
            }
        });
        try {
            return result.get();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new InternalError("Request interrupted");
        } catch (ExecutionException e) {
            if (e.getCause() instanceof A2AError error) throw error;
            throw new InternalError("Skill execution failed");
        } finally {
            if (subscription.get() != null) subscription.get().cancel();
            context.invokeEventConsumerCancelCallback();
        }
    }

    private void validateEmbeddedPush(MessageSendParams request, ServerCallContext context) {
        if (request.configuration() != null && request.configuration().taskPushNotificationConfig() != null) {
            if (!context.getUser().isAuthenticated()) {
                throw new InvalidParamsError("Push notifications require authentication");
            }
            configs.validate(request.configuration().taskPushNotificationConfig());
        }
    }

    private <T> T decode(JsonNode params, Class<T> type) {
        try {
            if (!params.isObject()) throw new IllegalArgumentException();
            var normalized = (com.fasterxml.jackson.databind.node.ObjectNode) params.deepCopy();
            // SDK records retain the pre-1.0 name here; the wire uses taskId.
            if (type == ListTaskPushNotificationConfigsParams.class) {
                normalized.set("id", params.path("taskId"));
            }
            if ((type == DeleteTaskPushNotificationConfigParams.class || type == GetTaskPushNotificationConfigParams.class)
                    && !normalized.hasNonNull("id")) {
                normalized.set("id", params.path("taskId"));
            }
            // SDK's record constructor requires metadata even though it is optional on the wire.
            if (type == CancelTaskParams.class && !normalized.hasNonNull("metadata")) {
                normalized.putObject("metadata");
            }
            return JsonUtil.fromJson(normalized.toString(), type);
        } catch (Exception e) {
            throw new InvalidParamsError("Invalid request parameters");
        }
    }

    @Override
    public void close() {
        workers.shutdownNow();
        consumers.shutdownNow();
        pushes.shutdownNow();
        processor.close();
    }

    /** Validates every path, including configs embedded in SendMessage. */
    private static final class ValidatedPushStore extends InMemoryPushNotificationConfigStore {
        private final PublicWebhookClient callbacks;

        ValidatedPushStore(PublicWebhookClient callbacks) {
            this.callbacks = callbacks;
        }

        @Override
        public TaskPushNotificationConfig setInfo(TaskPushNotificationConfig config) {
            validate(config);
            return super.setInfo(config);
        }

        @Override
        public TaskPushNotificationConfig setInfo(TaskPushNotificationConfig config, String version) {
            validate(config);
            return super.setInfo(config, version);
        }

        private void validate(TaskPushNotificationConfig config) {
            try {
                callbacks.validate(config.url());
                if (config.token() != null && (config.token().contains("\r") || config.token().contains("\n"))) {
                    throw new IllegalArgumentException();
                }
                if (config.authentication() != null) {
                    String value = config.authentication().scheme() + " " + config.authentication().credentials();
                    if (value.contains("\r") || value.contains("\n")) throw new IllegalArgumentException();
                }
            } catch (IllegalArgumentException e) {
                throw new InvalidParamsError("Invalid push notification URL or credentials");
            }
        }
    }

    // The SDK exposes start()/run(), but its CDI shutdown method is package-private.
    // Own the processor thread so standalone shutdown can interrupt and join it.
    private static final class ManagedProcessor extends MainEventBusProcessor implements AutoCloseable {
        private Thread thread;

        ManagedProcessor(MainEventBus bus, InMemoryTaskStore tasks, PushNotificationSender sender,
                         InMemoryQueueManager queues) {
            super(bus, tasks, sender, queues);
        }

        @Override
        public synchronized void start() {
            if (thread != null) return;
            thread = new Thread(this, "a2a-lite-events");
            thread.setDaemon(true);
            thread.start();
        }

        @Override
        public void close() {
            if (thread != null) {
                thread.interrupt();
                try {
                    thread.join(5000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }
    }
}
