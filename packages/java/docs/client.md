# Calling a remote agent from Java

`AgentNetwork` is a JSON-RPC client for A2A 1.0. Register the discovery base for a remote agent, then fetch its card. By default the client selects the first compatible HTTP(S) JSON-RPC interface on the same origin. A tenant-scoped view prefers a matching interface anywhere in the card and can use a tenantless interface when no match exists. It sends requests to the advertised path and includes the interface's tenant in every operation. Rediscovery uses the original base URL.

```java
var network = new AgentNetwork();
network.withCredentials(baseUrl, destination -> Map.of("Authorization", "Bearer " + currentToken()));
network.add("worker", baseUrl);
var card = network.discoverNamed("worker");
var handle = network.callWithHandle("worker", "generate", Map.of("topic", "birds"), 30);
```

Use `network.call(...)` for a skill that returns a Message. The Java handle API requires a Task result, including when a Message refers to an existing task ID. A task-producing skill can return a handle with its own task ID, endpoint and tenant. A handle keeps that route through rediscovery and looks up the current credentials on each request. Use the registered name or original discovery base for subsequent calls. Calls through a discovered interface with no tenant omit the field. For a known endpoint without a card, `network.withTenant("acme")` returns a scoped view for that tenant.

## Reading streams

`stream` and `streamRemoteSkill` yield text chunks. `streamEvents` yields complete A2A events, including vendor metadata, non-text parts, status messages and artifact updates. To follow a task that is still running, open a subscription with its handle or call `network.subscribeTask("worker", taskId)` with an ID from an initial task snapshot or a task listing.

```java
try (var events = handle.subscribeEvents()) {
    for (var event : events) {
        if (event.get("artifactUpdate") instanceof Map<?, ?> update) {
            System.out.println(update.get("artifact"));
        } else if (event.get("statusUpdate") instanceof Map<?, ?> update) {
            System.out.println(update.get("status"));
        } else if (event.containsKey("task")) {
            System.out.println(event.get("task"));
        } else if (event.containsKey("message")) {
            System.out.println(event.get("message"));
        }
    }
} catch (RemoteAgentException failure) {
    System.err.println(failure.getMessage());
    if (failure.getCode() != null) System.err.println(failure.getCode());
}
```

A subscription begins with the requested Task snapshot. Every subsequent update must identify the same task. When a task requires input or authentication, the peer can close the stream or send further updates on the same subscription. A terminal task state or a standalone Message completes the iterator immediately. To reconnect after a disconnect, open another subscription and use `handle.get()` for the full task snapshot. Use try-with-resources so leaving the loop early closes the HTTP body. Closing a stream releases the subscription. To request task cancellation, call `handle.cancel()`.

The structured stream delivers failed task states as events. The text stream raises `RemoteAgentException` for a failed task. Both raise this exception for a JSON-RPC error or a premature end of stream. Chunks delivered before the error stay available to the caller. JSON-RPC errors expose their code and optional data through `getCode()` and `getData()`.

For push delivery, `handle.subscribe(webhookUrl)` registers a webhook and `handle.unsubscribe()` removes it.

## Paging through tasks

`listTasks` accepts a registered name or an endpoint URL, page size and cursor. Pass the opaque cursor from each page into the next request. Each list entry contains the full task fields sent by the peer.

```java
String cursor = "";
do {
    var page = network.listTasks("worker", 25, cursor);
    for (var task : page.tasks()) System.out.println(task.get("id"));
    cursor = page.nextPageToken();
} while (!cursor.isEmpty());
```
