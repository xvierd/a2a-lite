package com.a2alite;

import com.a2alite.auth.AuthProvider;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.a2a.server.agentexecution.AgentExecutor;
import io.a2a.server.agentexecution.RequestContext;
import io.a2a.server.events.EventQueue;
import io.a2a.server.tasks.TaskUpdater;
import io.a2a.spec.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BiConsumer;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Lite executor that wraps skill handlers into the A2A SDK's AgentExecutor interface.
 *
 * This bridges a2a-lite's simple skill registration with the official A2A Java SDK.
 */
public class LiteAgentExecutor implements AgentExecutor {
    private static final Logger LOGGER = Logger.getLogger(LiteAgentExecutor.class.getName());

    private final Map<String, SkillDefinition> skills;
    private final List<Middleware> middlewares;
    private final List<BiConsumer<String, Object>> completeHooks;
    private final AuthProvider authProvider;
    private final ObjectMapper mapper = new ObjectMapper();

    public LiteAgentExecutor(
            Map<String, SkillDefinition> skills,
            List<Middleware> middlewares,
            List<BiConsumer<String, Object>> completeHooks,
            AuthProvider authProvider
    ) {
        this.skills = skills;
        this.middlewares = middlewares;
        this.completeHooks = completeHooks;
        this.authProvider = authProvider;
    }

    @Override
    public void execute(RequestContext context, EventQueue eventQueue) throws JSONRPCError {
        TaskUpdater updater = new TaskUpdater(context, eventQueue);

        try {
            // Start the task if new
            if (context.getTask() == null) {
                updater.submit();
            }
            updater.startWork();

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

            updater.complete();

        } catch (Exception e) {
            // Send error response
            try {
                String errorJson = mapper.writeValueAsString(Map.of(
                    "error", e.getMessage(),
                    "type", e.getClass().getSimpleName()
                ));
                TextPart errorPart = new TextPart(errorJson, null);
                updater.addArtifact(List.of(errorPart), null, null, null);
                updater.fail();
            } catch (Exception ex) {
                throw new RuntimeException("Failed to serialize error: " + ex.getMessage(), ex);
            }
        }
    }

    @Override
    public void cancel(RequestContext context, EventQueue eventQueue) throws JSONRPCError {
        Task task = context.getTask();

        if (task != null && (task.getStatus().state() == TaskState.CANCELED ||
                           task.getStatus().state() == TaskState.COMPLETED)) {
            throw new TaskNotCancelableError();
        }

        TaskUpdater updater = new TaskUpdater(context, eventQueue);
        updater.cancel();
    }

    private Object executeSkill(String skillName, Map<String, Object> params) throws Exception {
        // Default to first skill only if there's exactly one
        if (skillName == null || skillName.isEmpty()) {
            if (skills.isEmpty()) {
                return Map.of("error", "No skills registered");
            }
            if (skills.size() == 1) {
                skillName = skills.keySet().iterator().next();
            } else {
                return Map.of(
                    "error", "No skill specified. Use {\"skill\": \"name\", \"params\": {...}} format.",
                    "availableSkills", skills.keySet()
                );
            }
        }

        var skillDef = skills.get(skillName);
        if (skillDef == null) {
            return Map.of(
                "error", "Unknown skill: " + skillName,
                "availableSkills", skills.keySet()
            );
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
