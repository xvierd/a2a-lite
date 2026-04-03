import com.a2alite.Agent;
import com.a2alite.AgentNetwork;

import java.util.Map;

/**
 * TaskHandle and Agent Card Discovery demo.
 *
 * Two agents collaborate:
 *   - DataAgent      (port 8787) — stores and retrieves data
 *   - Orchestrator   (port 8788) — discovers DataAgent, delegates with handle,
 *                                  then checks task status
 *
 * Run in separate terminals:
 *   Terminal 1: java 15_TaskHandleDiscovery.java data
 *   Terminal 2: java 15_TaskHandleDiscovery.java orchestrator
 */
class TaskHandleDiscovery {

    /**
     * DataAgent: a simple agent that stores key-value pairs.
     */
    static Agent createDataAgent() {
        var agent = Agent.builder()
            .name("DataAgent")
            .description("Stores and retrieves key-value data")
            .version("1.0.0")
            .build();

        // Skill: store a key-value pair and return confirmation
        agent.skill("store", params -> {
            String key = (String) params.get("key");
            Object value = params.get("value");
            System.out.println("  [DataAgent] Stored: " + key + " = " + value);
            return Map.of("stored", true, "key", key, "value", value);
        });

        // Skill: retrieve a value by key (simulated)
        agent.skill("retrieve", params -> {
            String key = (String) params.get("key");
            return Map.of("key", key, "value", "cached-value-for-" + key);
        });

        return agent;
    }

    /**
     * OrchestratorAgent: discovers DataAgent and uses TaskHandle for delegation.
     */
    static Agent createOrchestratorAgent() {
        var network = new AgentNetwork();
        network.add("data", "http://localhost:8787");

        var orchestrator = Agent.builder()
            .name("Orchestrator")
            .description("Coordinates data operations with task tracking")
            .network(network)
            .build();

        orchestrator.skill("process", params -> {
            String key = (String) params.get("key");
            Object value = params.get("value");

            // Step 1: Discover DataAgent's capabilities
            // This fetches /.well-known/agent.json from the remote agent
            try {
                System.out.println("  [Orchestrator] Discovering DataAgent...");
                var card = network.discoverAgent("http://localhost:8787");
                System.out.println("  [Orchestrator] Discovered: " + card.getName()
                    + " v" + card.getVersion());
                System.out.println("  [Orchestrator] Skills: " + card.getSkills().size());
                System.out.println("  [Orchestrator] Streaming: " + card.isSupportsStreaming());
            } catch (Exception e) {
                System.out.println("  [Orchestrator] Discovery failed (agent may not support it): "
                    + e.getMessage());
            }

            // Step 2: Delegate with handle to get the remote task ID
            // delegateWithHandle() returns a TaskHandle instead of a raw Object
            try {
                System.out.println("  [Orchestrator] Delegating store operation...");
                var handle = orchestrator.delegateWithHandle(
                    "data", "store", Map.of("key", key, "value", value)
                );

                System.out.println("  [Orchestrator] Task ID: " + handle.getTaskId());
                System.out.println("  [Orchestrator] Result:  " + handle.getResult());
                System.out.println("  [Orchestrator] Agent:   " + handle.getAgentUrl());

                // Step 3: Check status via the handle's convenience method
                if (handle.getTaskId() != null) {
                    System.out.println("  [Orchestrator] Checking task status via handle...");
                    var taskStatus = handle.getStatus();
                    System.out.println("  [Orchestrator] Task status: " + taskStatus);

                    // Or check status via the network's name-based method
                    System.out.println("  [Orchestrator] Checking task status via network...");
                    var taskStatus2 = network.getTask("data", handle.getTaskId());
                    System.out.println("  [Orchestrator] Task status: " + taskStatus2);

                    // Cancel if needed:
                    // handle.cancel();
                    // network.cancelTask("data", handle.getTaskId());
                }

                return Map.of(
                    "processed", true,
                    "taskId", handle.getTaskId() != null ? handle.getTaskId() : "unknown",
                    "result", handle.getResult()
                );
            } catch (Exception e) {
                return Map.of("error", e.getMessage());
            }
        });

        return orchestrator;
    }

    public static void main(String[] args) {
        String role = args.length > 0 ? args[0] : "orchestrator";

        switch (role) {
            case "data" -> {
                System.out.println("Starting DataAgent on port 8787...");
                createDataAgent().run(8787);
            }
            default -> {
                System.out.println("Starting Orchestrator on port 8788...");
                System.out.println("Make sure DataAgent (8787) is running.");
                createOrchestratorAgent().run(8788);
            }
        }
    }
}
