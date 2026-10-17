package com.a2alite;

import com.a2alite.auth.AuthProvider;
import com.a2alite.errors.A2ALiteException;
import com.a2alite.errors.SkillNotFoundException;
import com.a2alite.push.TaskPushRegistry;
import com.a2alite.push.PublicWebhookClient;
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

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.BiConsumer;
import java.util.function.Function;
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
    private final Map<String, Execution> executions = new ConcurrentHashMap<>();
    private final ObjectMapper mapper = new ObjectMapper();
    private final PublicWebhookClient callbacks = new PublicWebhookClient();
    private final Function<Exception, Object> errorHandler;
    private final Map<String, SkillHandlerWithContext> contextualSkills;

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
        this(skills, middlewares, completeHooks, authProvider, pushRegistry, null);
    }

    public LiteAgentExecutor(Map<String, SkillDefinition> skills, List<Middleware> middlewares,
            List<BiConsumer<String, Object>> completeHooks, AuthProvider authProvider,
            TaskPushRegistry pushRegistry, Function<Exception, Object> errorHandler) {
        this(skills, middlewares, completeHooks, authProvider, pushRegistry, errorHandler, Map.of());
    }

    public LiteAgentExecutor(Map<String, SkillDefinition> skills, List<Middleware> middlewares,
            List<BiConsumer<String, Object>> completeHooks, AuthProvider authProvider,
            TaskPushRegistry pushRegistry, Function<Exception, Object> errorHandler,
            Map<String, SkillHandlerWithContext> contextualSkills) {
        this.contextualSkills = contextualSkills;
        this.errorHandler = errorHandler;
        this.skills = skills;
        this.middlewares = middlewares;
        this.completeHooks = completeHooks;
        this.authProvider = authProvider;
        this.pushRegistry = pushRegistry;
    }

    @Override
    public void execute(RequestContext context, AgentEmitter emitter) throws A2AError {
        var execution = new Execution(Thread.currentThread());
        executions.put(context.getTaskId(), execution);
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

            if ((skillName == null || skillName.isEmpty()) && skills.size() == 1) {
                skillName = skills.keySet().iterator().next();
            }
            var definition = skills.get(skillName);
            boolean taskMode = context.getTask() != null
                || (definition != null && (definition.isStreaming() || definition.needsTaskContext()))
                || (context.getConfiguration() != null
                    && (Boolean.TRUE.equals(context.getConfiguration().returnImmediately())
                        || context.getConfiguration().taskPushNotificationConfig() != null));
            if (taskMode) startTask(context, emitter, execution);

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
            MiddlewareNext finalHandler = () -> executeSkill(hookedSkillName, ctx.params(), context, emitter, execution);

            MiddlewareNext handler = finalHandler;
            for (int i = middlewares.size() - 1; i >= 0; i--) {
                var middleware = middlewares.get(i);
                var next = handler;
                handler = () -> middleware.apply(ctx, next);
            }

            Object result = handler.call();

            if (result instanceof StreamingHandler.StreamResult streamResult) {
                execution.stream = streamResult;
                // Streaming skill: task first, then one status update per chunk
                if (!taskMode) startTask(context, emitter, execution);
                for (var chunk : streamResult) {
                    if (execution.canceled.get() || execution.outputFinished) break;
                    String chunkText = chunk instanceof String s ? s : String.valueOf(chunk);
                    emitter.updateStatus(TaskState.TASK_STATE_WORKING,
                        emitter.newAgentMessage(List.of(new TextPart(chunkText)), null));
                }
                if (!execution.canceled.get() && !execution.outputFinished) emitter.complete();
            } else {
                // Non-streaming skill: a single agent message
                String responseText;
                if (result instanceof String) {
                    responseText = (String) result;
                } else {
                    responseText = mapper.writeValueAsString(result);
                }
                if (!execution.canceled.get() && !execution.outputFinished) {
                    if (taskMode) emitter.complete(emitter.newAgentMessage(List.of(new TextPart(responseText)), null));
                    else emitter.sendMessage(responseText);
                }
            }

            if (execution.canceled.get()) return;

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
            if (!execution.canceled.get() && !execution.outputFinished) handleExecutionError(context, emitter, execution, e);
        } finally {
            if (execution.stream != null) execution.stream.close();
            executions.remove(context.getTaskId(), execution);
        }
    }

    private void startTask(RequestContext context, AgentEmitter emitter, Execution execution) {
        if (context.getTask() == null) {
            emitter.addTask(emitter.taskBuilder()
                .status(new org.a2aproject.sdk.spec.TaskStatus(TaskState.TASK_STATE_SUBMITTED))
                .history(List.of(context.getMessage())).build());
        } else {
            emitter.addTask(context.getTask());
        }
        execution.taskStarted = true;
        emitter.startWork();
    }

    @Override
    public void cancel(RequestContext context, AgentEmitter emitter) throws A2AError {
        org.a2aproject.sdk.spec.Task task = context.getTask();

        if (task != null && task.status().state().isFinal()) {
            throw new TaskNotCancelableError();
        }

        Execution execution = executions.get(context.getTaskId());
        if (execution != null) execution.canceled.set(true);
        emitter.cancel();
        if (execution != null) {
            if (execution.stream != null) execution.stream.close();
            execution.thread.interrupt();
        }
    }

    private static final class Execution {
        private final Thread thread;
        private final AtomicBoolean canceled = new AtomicBoolean();
        private volatile StreamingHandler.StreamResult stream;
        private volatile boolean outputFinished;
        private boolean taskStarted;

        Execution(Thread thread) { this.thread = thread; }
    }

    /**
     * Serializes the error and fails the task (or the request) with an agent
     * message carrying the error details.
     *
     * @param emitter the agent emitter
     * @param e       the exception that caused the failure
     */
    private void handleExecutionError(RequestContext context, AgentEmitter emitter, Execution execution, Exception e) {
        try {
            if (!execution.taskStarted) startTask(context, emitter, execution);
            Object errorResult;
            if (errorHandler != null) {
                errorResult = errorHandler.apply(e);
            } else if (e instanceof A2ALiteException a2aErr) {
                errorResult = a2aErr.toResponse();
            } else {
                errorResult = Map.of("error", e.getMessage() != null ? e.getMessage() : "Skill execution failed",
                    "type", e.getClass().getSimpleName());
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
            var headers = new HashMap<String, String>();
            if (config.token() != null) headers.put("Authorization", "Bearer " + config.token());
            callbacks.post(config.url(), body, headers);
        } catch (Exception e) {
            LOGGER.log(Level.WARNING, "Per-task push notification failed: " + e.getClass().getSimpleName());
        }
    }

    private Object executeSkill(String skillName, Map<String, Object> params, RequestContext request,
                                AgentEmitter emitter, Execution execution) throws Exception {
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

        var contextualHandler = contextualSkills.get(skillName);
        if (contextualHandler != null) {
            var task = new Task(request.getTaskId(), skillName, params, new TaskStatus(com.a2alite.TaskState.WORKING));
            var context = new TaskContext(task);
            context.onStatusChange(status -> {
                if (execution.canceled.get() || execution.outputFinished) return;
                var state = TaskState.valueOf("TASK_STATE_" + status.state().name());
                var parts = status.message() == null ? List.<Part<?>>of() : List.<Part<?>>of(new TextPart(status.message()));
                var metadata = status.progress() == null ? null : Map.<String, Object>of("progress", status.progress());
                var message = parts.isEmpty() && metadata == null ? null : emitter.newAgentMessage(parts, metadata);
                emitter.updateStatus(state, message);
                execution.outputFinished = state.isFinal() || state == TaskState.TASK_STATE_INPUT_REQUIRED
                    || state == TaskState.TASK_STATE_AUTH_REQUIRED;
            });
            return contextualHandler.handle(params, context);
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
