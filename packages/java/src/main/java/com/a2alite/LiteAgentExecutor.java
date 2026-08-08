package com.a2alite;

import com.a2alite.auth.AuthProvider;
import com.a2alite.errors.A2ALiteException;
import com.a2alite.errors.SkillNotFoundException;
import com.a2alite.push.TaskPushRegistry;
import com.a2alite.streaming.StreamingHandler;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.a2aproject.sdk.server.agentexecution.AgentExecutor;
import org.a2aproject.sdk.server.agentexecution.RequestContext;
import org.a2aproject.sdk.server.tasks.AgentEmitter;
import org.a2aproject.sdk.spec.A2AError;
import org.a2aproject.sdk.spec.Message;
import org.a2aproject.sdk.spec.Part;
import org.a2aproject.sdk.spec.TaskNotCancelableError;
import org.a2aproject.sdk.spec.TaskState;
import org.a2aproject.sdk.spec.TextPart;

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
 * <p>This bridges a2a-lite's simple skill registration with the official A2A Java SDK
 * (protocol v1.0, {@code org.a2aproject.sdk}).
 *
 * <p>Event rules (enforced by the SDK's event queue):
 * <ul>
 *   <li>Non-streaming skills: a single agent {@link Message} is sent.</li>
 *   <li>Streaming skills: {@code submit()} (for new tasks) → {@code startWork()} →
 *       one {@code updateStatus(TASK_STATE_WORKING, message)} per chunk → {@code complete()}.</li>
 * </ul>
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
    public void execute(RequestContext context, AgentEmitter emitter) throws A2AError {
        String finalSkillName = null;
        try {
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
            finalSkillName = skillName;
            final String hookedSkillName = finalSkillName;
            MiddlewareNext finalHandler = () -> executeSkill(hookedSkillName, ctx.params());

            MiddlewareNext handler = finalHandler;
            for (int i = middlewares.size() - 1; i >= 0; i--) {
                var middleware = middlewares.get(i);
                var next = handler;
                handler = () -> middleware.apply(ctx, next);
            }

            Object result = handler.call();

            if (result instanceof StreamingHandler.StreamResult streamResult) {
                // Streaming skill: task first, then one status update per chunk
                if (context.getTask() == null) {
                    emitter.submit();
                }
                emitter.startWork();
                for (var chunk : streamResult) {
                    String chunkText = chunk instanceof String s ? s : String.valueOf(chunk);
                    emitter.updateStatus(TaskState.TASK_STATE_WORKING,
                        emitter.newAgentMessage(List.of(new TextPart(chunkText)), null));
                }
                emitter.complete();
            } else {
                // Non-streaming skill: a single agent message
                String responseText;
                if (result instanceof String) {
                    responseText = (String) result;
                } else {
                    responseText = mapper.writeValueAsString(result);
                }
                emitter.sendMessage(responseText);
            }

            // Call completion hooks
            for (var hook : completeHooks) {
                try {
                    hook.accept(hookedSkillName, result);
                } catch (Exception e) {
                    LOGGER.log(Level.WARNING, "Completion hook error for skill '" + hookedSkillName + "'", e);
                }
            }

            // Fire per-task push notification if registered
            if (pushRegistry != null && context.getTask() != null) {
                String taskId = context.getTask().id();
                if (taskId != null) {
                    pushRegistry.get(taskId).ifPresent(config ->
                        fireTaskWebhook(config, taskId, hookedSkillName, result)
                    );
                }
            }

        } catch (Exception e) {
            handleExecutionError(emitter, e);
        }
    }

    @Override
    public void cancel(RequestContext context, AgentEmitter emitter) throws A2AError {
        org.a2aproject.sdk.spec.Task task = context.getTask();

        if (task != null && (task.status().state() == TaskState.TASK_STATE_CANCELED ||
                           task.status().state() == TaskState.TASK_STATE_COMPLETED)) {
            throw new TaskNotCancelableError();
        }

        emitter.cancel();
    }

    /**
     * Serializes the error and fails the task (or the request) with an agent
     * message carrying the error details.
     *
     * @param emitter the agent emitter
     * @param e       the exception that caused the failure
     */
    private void handleExecutionError(AgentEmitter emitter, Exception e) {
        try {
            Map<String, Object> errorResult;
            if (e instanceof A2ALiteException a2aErr) {
                errorResult = a2aErr.toResponse();
            } else {
                errorResult = Map.of("error", e.getMessage(), "type", e.getClass().getSimpleName());
            }
            String errorJson = mapper.writeValueAsString(errorResult);
            Message errorMessage = emitter.newAgentMessage(List.of(new TextPart(errorJson)), null);
            emitter.fail(errorMessage);
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
        if (message != null && message.parts() != null) {
            for (Part<?> part : message.parts()) {
                if (part instanceof TextPart textPart) {
                    textBuilder.append(textPart.text());
                }
            }
        }
        return textBuilder.toString();
    }
}
