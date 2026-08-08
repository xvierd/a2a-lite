package com.a2alite;

import com.fasterxml.jackson.databind.ObjectMapper;

import java.lang.reflect.Proxy;
import java.util.*;
import java.util.logging.Logger;

/**
 * Path-based router that mounts multiple A2A agents under a single Javalin server.
 *
 * Requires Javalin on the classpath (same as {@link Agent#run()}).
 *
 * <pre>{@code
 * var router = new AgentRouter();
 * router.mount("/weather", weatherAgent);
 * router.mount("/hotels", hotelAgent);
 * router.run(8787);
 * }</pre>
 *
 * A merged agent card (A2A protocol v1.0) is served at
 * {@code /.well-known/agent-card.json}.
 */
public class AgentRouter {
    private static final Logger LOGGER = Logger.getLogger(AgentRouter.class.getName());
    private static final String PROTOCOL_VERSION = "1.0";

    private final List<String> prefixes = new ArrayList<>();
    private final Map<String, Agent> agents = new LinkedHashMap<>();
    private final ObjectMapper mapper = new ObjectMapper();

    public AgentRouter mount(String prefix, Agent agent) {
        if (!prefix.startsWith("/")) prefix = "/" + prefix;
        prefix = prefix.replaceAll("/$", "");
        prefixes.add(prefix);
        agents.put(prefix, agent);
        return this;
    }

    public Map<String, Object> buildMergedCard(String host, int port) {
        var allSkills = new ArrayList<Map<String, Object>>();
        var names = new ArrayList<String>();
        var descriptions = new ArrayList<String>();
        var hasStreaming = new boolean[]{false};

        for (var entry : agents.entrySet()) {
            var prefix = entry.getKey();
            var agent = entry.getValue();
            names.add(agent.getName());
            descriptions.add(agent.getDescription());
            for (var skill : agent.getSkills().values()) {
                if (skill.isStreaming()) hasStreaming[0] = true;
                var skillMap = new LinkedHashMap<String, Object>();
                skillMap.put("id", prefix.replaceAll("^/", "") + "/" + skill.name());
                skillMap.put("name", skill.name());
                skillMap.put("description", "[" + agent.getName() + "] " + skill.description());
                skillMap.put("tags", skill.tags());
                allSkills.add(skillMap);
            }
        }

        var card = new LinkedHashMap<String, Object>();
        card.put("name", String.join(" + ", names));
        card.put("description", String.join("; ", descriptions));
        card.put("version", "1.0.0");
        var routerUrl = "http://" + host + ":" + port;
        card.put("supportedInterfaces", List.of(
            Map.of("protocolBinding", "JSONRPC", "url", routerUrl, "protocolVersion", PROTOCOL_VERSION),
            Map.of("protocolBinding", "HTTP+JSON", "url", routerUrl, "protocolVersion", PROTOCOL_VERSION)));
        card.put("capabilities", Map.of("streaming", hasStreaming[0], "pushNotifications", false));
        card.put("defaultInputModes", List.of("application/json"));
        card.put("defaultOutputModes", List.of("application/json"));
        card.put("skills", allSkills);
        return card;
    }

    public void run() { run("0.0.0.0", 8787); }
    public void run(int port) { run("0.0.0.0", port); }

    public void run(String host, int port) {
        var displayHost = "0.0.0.0".equals(host) ? "localhost" : host;
        try {
            var javalinClass = Class.forName("io.javalin.Javalin");
            var createMethod = javalinClass.getMethod("create");
            var app = createMethod.invoke(null);
            var handlerClass = Class.forName("io.javalin.http.Handler");
            var getMethod = javalinClass.getMethod("get", String.class, handlerClass);
            var postMethod = javalinClass.getMethod("post", String.class, handlerClass);

            // Merged card at root
            final var mergedCard = buildMergedCard(displayHost, port);
            getMethod.invoke(app, "/.well-known/agent-card.json",
                Proxy.newProxyInstance(handlerClass.getClassLoader(), new Class[]{handlerClass},
                    (proxy, method, args) -> {
                        if ("handle".equals(method.getName()))
                            args[0].getClass().getMethod("json", Object.class).invoke(args[0], mergedCard);
                        return null;
                    }));

            // Per-agent endpoints
            for (var prefix : prefixes) {
                final var agent = agents.get(prefix);
                final var p = prefix;

                // Agent card
                getMethod.invoke(app, p + "/.well-known/agent-card.json",
                    Proxy.newProxyInstance(handlerClass.getClassLoader(), new Class[]{handlerClass},
                        (proxy, method, args) -> {
                            if ("handle".equals(method.getName()))
                                args[0].getClass().getMethod("json", Object.class)
                                    .invoke(args[0], agent.buildAgentCardJson(displayHost, port));
                            return null;
                        }));

                // POST handler
                var agentPostHandler = Proxy.newProxyInstance(
                    handlerClass.getClassLoader(), new Class[]{handlerClass},
                    (proxy, method, args) -> {
                        if ("handle".equals(method.getName())) handleAgentPost(args[0], agent);
                        return null;
                    });
                postMethod.invoke(app, p, agentPostHandler);
                postMethod.invoke(app, p + "/*", agentPostHandler);
            }

            // Start
            System.out.printf("A2A Lite Router -> http://%s:%d%n", displayHost, port);
            for (var prefix : prefixes)
                System.out.printf("  %s -> %s (%d skills)%n",
                    prefix, agents.get(prefix).getName(), agents.get(prefix).getSkills().size());

            javalinClass.getMethod("start", String.class, int.class).invoke(app, host, port);

        } catch (ClassNotFoundException e) {
            throw new RuntimeException("Javalin not found. Add 'io.javalin:javalin'.", e);
        } catch (Exception e) {
            throw new RuntimeException("Failed to start router: " + e.getMessage(), e);
        }
    }

    private void handleAgentPost(Object ctx, Agent agent) throws Exception {
        var body = mapper.readTree((byte[]) ctx.getClass().getMethod("bodyAsBytes").invoke(ctx));
        var id = body.path("id").asText();
        var jsonMethod = ctx.getClass().getMethod("json", Object.class);

        if ("SendMessage".equals(body.path("method").asText())) {
            var result = agent.handleMessage(body.path("params").path("message"),
                                             Collections.emptyMap());
            var response = mapper.createObjectNode();
            response.put("jsonrpc", "2.0");
            response.put("id", id);
            var message = response.putObject("result").putObject("message");
            message.put("role", "ROLE_AGENT");
            message.put("messageId", java.util.UUID.randomUUID().toString().replace("-", ""));
            message.putArray("parts").addObject()
                .put("text", mapper.writeValueAsString(result));
            jsonMethod.invoke(ctx, response);
        } else {
            var response = mapper.createObjectNode();
            response.put("jsonrpc", "2.0");
            response.put("id", id);
            var err = response.putObject("error");
            err.put("code", -32601);
            err.put("message", "Method not found");
            jsonMethod.invoke(ctx, response);
        }
    }
}
