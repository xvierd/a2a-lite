import com.a2alite.Agent;
import com.a2alite.AgentNetwork;

import java.util.Map;

/**
 * Per-task push notification demo.
 *
 * A WorkerAgent on port 8787 processes tasks. A client delegates a skill call,
 * then registers a per-task webhook via handle.subscribe(). When the task
 * completes, the WorkerAgent fires an HTTP POST to the registered webhook URL.
 *
 * Flow:
 *   1. Client calls agent.delegateWithHandle("worker", "process", params)
 *   2. Client calls handle.subscribe("http://localhost:9000/webhook")
 *      - This sends a tasks/pushNotification/set JSON-RPC request to the agent
 *      - The agent stores the webhook URL keyed by task ID
 *   3. When the task completes, the agent's executor checks the TaskPushRegistry
 *      and fires an HTTP POST to the registered webhook with task_id, skill,
 *      result, status, and timestamp
 *   4. Client can also call handle.getPushConfig() to inspect or
 *      handle.unsubscribe() to remove the webhook
 *
 * Run:
 *   Terminal 1: java 21_PerTaskPush.java worker
 *   Terminal 2: java 21_PerTaskPush.java client
 */
class PerTaskPush {

    /**
     * WorkerAgent: a simple agent that processes tasks with a short delay.
     */
    static Agent createWorkerAgent() {
        var agent = Agent.builder()
            .name("WorkerAgent")
            .description("Processes tasks and fires per-task webhooks on completion")
            .version("1.0.0")
            .build();

        agent.skill("process", params -> {
            String item = (String) params.getOrDefault("item", "unknown");
            // Simulate some processing time
            Thread.sleep(1000);
            return Map.of(
                "item", item,
                "processed", true,
                "message", "Successfully processed: " + item
            );
        });

        return agent;
    }

    /**
     * Client: delegates to the worker, subscribes to push notifications,
     * then inspects and cleans up.
     */
    static void runClient() throws Exception {
        var network = new AgentNetwork();
        network.add("worker", "http://localhost:8787");

        var agent = Agent.builder()
            .name("ClientAgent")
            .description("Orchestrates work and subscribes to push notifications")
            .network(network)
            .build();

        // Step 1: Delegate with handle to get the task ID back
        System.out.println("Delegating task to WorkerAgent...");
        var handle = agent.delegateWithHandle("worker", "process",
            Map.of("item", "report-2024"));

        System.out.println("Task ID: " + handle.getTaskId());
        System.out.println("Result: " + handle.getResult());

        // Step 2: Subscribe to push notifications for this task
        // In a real scenario, you would register the webhook BEFORE the task
        // completes. Here we demonstrate the API even though the task already
        // finished synchronously.
        System.out.println("\nSubscribing to push notifications...");
        var subscribeResult = handle.subscribe("http://localhost:9000/webhook");
        System.out.println("Subscribe result: " + subscribeResult);

        // Step 3: Inspect the registered push config
        System.out.println("\nRetrieving push config...");
        var pushConfig = handle.getPushConfig();
        System.out.println("Push config: " + pushConfig);

        // Step 4: Unsubscribe (clean up)
        System.out.println("\nUnsubscribing...");
        var unsubResult = handle.unsubscribe();
        System.out.println("Unsubscribe result: " + unsubResult);

        System.out.println("\nDone.");
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            System.out.println("Usage: java 21_PerTaskPush.java [worker|client]");
            return;
        }

        switch (args[0]) {
            case "worker" -> createWorkerAgent().run(8787);
            case "client" -> runClient();
            default -> System.out.println("Unknown role: " + args[0]);
        }
    }
}
