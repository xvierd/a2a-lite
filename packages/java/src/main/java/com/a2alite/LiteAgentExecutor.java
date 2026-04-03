package com.a2alite;

import com.a2alite.auth.AuthProvider;
import com.a2alite.errors.A2ALiteException;
import com.a2alite.errors.SkillNotFoundException;
import com.a2alite.push.TaskPushRegistry;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.a2a.server.agentexecution.AgentExecutor;
import io.a2a.server.agentexecution.RequestContext;
import io.a2a.server.events.EventQueue;
import io.a2a.server.tasks.TaskUpdater;
import io.a2a.spec.*;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BiConsumer;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Lite executor that wraps skill handlers into the A2A SDK's AgentExecutor interface.
 *
 * <p>This bridges a2a-lite's simple skill registration with the official A2A Java SDK.
 */
public class LiteAgentExecutor implements AgentExecutor {
    private static final Logger LOGGER = Logger.getLogger(LiteAgentExecutor.class.getName());

    private final Map<String, SkillDefinition> skills;
    private final List<Middleware> middlewares;
    private final List<BiConsumer<String, Object>> completeHooks;
    private final AuthProvider authProvider;
    private final TaskPushRegistry pushRegistry;
    private final ObjectMapper mapper = new ObjectMapper();
    private final HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    public LiteAgentExecutor(
            Map<String, SkillDefinition> skills,
            List<Middleware> middlewares,
            List<BiConsumer<String, Object>> completeHooks,
            AuthProvider authProvider
    ) {
        this(skills, middlewares, completeHooks, authProvider, null);
    }

    public LiteAgentExecutor(
            Map<String, SkillDefinition> skills,
            List<Middleware> middlewares,
            List<BiConsumer<String, Object>> completeHooks,
            AuthProvider authProvider,
            TaskPushRegistry pushRegistry
    ) {
        this.skills = skills;
        this.middlewares = middlewares;
        this.completeHooks = completeHooks;
        this.authProvider = authProvider;
        this.pushRegistry = pushRegistry;
    }

    @Override
    public void execute(RequestContext context, EventQueue eventQueue) throws JSONRPCError {
        TaskUpdater updater = new TaskUpdater(context, eventQueue);

        try {
            initializeTaskState(context, updater);

            // Extract message text
            String text = extractTextFromMessage(context.getMessage());

            // Parse skill call
            String skillName = null;
            Map<String, Object> params = new HashMap<>();

            try {
                var parsed = mapper.readTree(text);
                if (parsed.has("skill")) {
                    skillName = parsed.path("skill").asText();
                    if (parsed.has("params")) {
                        params = mapper.convertValue(parsed.path("params"), Map.class);
                    }
                }
            } catch (Exception e) {
                LOGGER.fine("Message is not JSON, treating as plain text");
                params.put("message", text);
            }

            // Build middleware context
            var ctx = new MiddlewareContext(
                skillName != null ? skillName : "",
                params,
                text,
                new HashMap<>()
            );

            // Execute through middleware chain
            final String finalSkillName = skillName;
            MiddlewareNext finalHandler = () -> executeSkill(finalSkillName, ctx.params());

            MiddlewareNext handler = finalHandler;
            for (int i = middlewares.size() - 1; i >= 0; i--) {
                var middleware = middlewares.get(i);
                var next = handler;
                handler = () -> middleware.apply(ctx, next);
            }

            Object result = handler.call();

            // Convert result to text
            String responseText;
            if (result instanceof String) {
                responseText = (String) result;
            } else {
                responseText = mapper.writeValueAsString(result);
            }

            // Send response as artifact
            TextPart responsePart = new TextPart(responseText, null);
            updater.addArtifact(List.of(responsePart), null, null, null);

            // Call completion hooks
            for (var hook : completeHooks) {
                try {
                    hook.accept(finalSkillName, result);
                } catch (Exception e) {
                    LOGGER.log(Level.WARNING, "Completion hook error for skill '" + finalSkillName + "'", e);
                }
            }

            // Fire per-task push notification if registered
            if (pushRegistry != null && context.getTask() != null) {
                String taskId = context.getTask().getId();
                if (taskId != null) {
                    pushRegistry.get(taskId).ifPresent(config ->
                        fireTaskWebhook(config, taskId, finalSkillName, result)
                    );
                }
            }

            updater.complete();

        } catch (Exception e) {
            handleExecutionError(updater, e);
        }
    }

    @Override
    public void cancel(RequestContext context, EventQueue eventQueue) throws JSONRPCError {
        io.a2a.spec.Task task = context.getTask();

        if (task != null && (task.getStatus().state() == io.a2a.spec.TaskState.CANCELED ||
                           task.getStatus().state() == io.a2a.spec.TaskState.COMPLETED)) {
            throw new TaskNotCancelableError();
        }

        TaskUpdater updater = new TaskUpdater(context, eventQueue);
        updater.cancel();
    }

    /**
     * Transitions the task to its initial working state. For new tasks (no prior
     * state recorded in the context) the task is first submitted, then started.
     * For resumed tasks it is started directly.
     *
     * @param context the request context
     * @param updater the task updater used to emit state transitions
     */
    private void initializeTaskState(RequestContext context, TaskUpdater updater) {
        if (context.getTask() == null) {
            updater.submit();
        }
        updater.startWork();
    }

    /**
     * Serializes and delivers an error result artifact, then marks the task as
     * failed. Wraps serialization failures in a {@link RuntimeException}.
     *
     * @param updater the task updater
     * @param e       the exception that caused the failure
     */
    private void handleExecutionError(TaskUpdater updater, Exception e) {
        try {
            Map<String, Object> errorResult;
            if (e instanceof A2ALiteException a2aErr) {
                errorResult = a2aErr.toResponse();
            } else {
                errorResult = Map.of("error", e.getMessage(), "type", e.getClass().getSimpleName());
            }
            String errorJson = mapper.writeValueAsString(errorResult);
            TextPart errorPart = new TextPart(errorJson, null);
            updater.addArtifact(List.of(errorPart), null, null, null);
            updater.fail();
        } catch (Exception ex) {
            throw new RuntimeException("Failed to serialize error: " + ex.getMessage(), ex);
        }
    }

    /**
     * Fires an HTTP POST to the per-task webhook registered for the given task.
     */
    private void fireTaskWebhook(TaskPushRegistry.PushConfig config, String taskId, String skillName, Object result) {
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("task_id", taskId);
        event.put("skill", skillName);
        event.put("result", result);
        event.put("status", "completed");
        event.put("timestamp", System.currentTimeMillis() / 1000.0);

        try {
            String body = mapper.writeValueAsString(event);
            var requestBuilder = HttpRequest.newBuilder()
                .uri(URI.create(config.url()))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .timeout(Duration.ofSeconds(10));
            if (config.token() != null) {
                requestBuilder.header("Authorization", "Bearer " + config.token());
            }
            httpClient.send(requestBuilder.build(), HttpResponse.BodyHandlers.discarding());
        } catch (Exception e) {
            LOGGER.log(Level.WARNING, "Per-task push notification failed for task " + taskId + ": " + e.getMessage());
        }
    }

    private Object executeSkill(String skillName, Map<String, Object> params) throws Exception {
        // Default to first skill only if there's exactly one
        if (skillName == null || skillName.isEmpty()) {
            if (skills.isEmpty()) {
                throw new SkillNotFoundException("", List.of());
            }
            if (skills.size() == 1) {
                skillName = skills.keySet().iterator().next();
            } else {
                throw new SkillNotFoundException("", new ArrayList<>(skills.keySet()));
            }
        }

        var skillDef = skills.get(skillName);
        if (skillDef == null) {
            throw new SkillNotFoundException(skillName, new ArrayList<>(skills.keySet()));
        }

        return skillDef.handler().handle(params);
    }

    private String extractTextFromMessage(Message message) {
        StringBuilder textBuilder = new StringBuilder();
        if (message.getParts() != null) {
            for (Part<?> part : message.getParts()) {
                if (part instanceof TextPart textPart) {
                    textBuilder.append(textPart.getText());
                }
            }
        }
        return textBuilder.toString();
    }
}
