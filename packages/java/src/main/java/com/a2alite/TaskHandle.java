package com.a2alite;

/**
 * Handle to a remote task, carrying the task ID, result, and agent URL.
 *
 * <p>Returned by {@link AgentNetwork#callRemoteSkillWithHandle} and
 * {@link Agent#delegateWithHandle} to give callers access to the remote
 * task ID for follow-up operations like {@code getRemoteTask} and
 * {@code cancelRemoteTask}.
 */
public class TaskHandle {
    private final String taskId;
    private final Object result;
    private final AgentNetwork.Endpoint endpoint;
    private final AgentNetwork network;

    public TaskHandle(String taskId, Object result, String agentUrl) {
        this(taskId, result, agentUrl, null);
    }

    public TaskHandle(String taskId, Object result, String agentUrl, AgentNetwork network) {
        this.taskId = taskId;
        this.result = result;
        this.network = network != null ? network : new AgentNetwork();
        this.endpoint = this.network.endpoint(agentUrl);
    }

    TaskHandle(String taskId, Object result, AgentNetwork.Endpoint endpoint, AgentNetwork network) {
        this.taskId = taskId;
        this.result = result;
        this.network = network;
        this.endpoint = endpoint;
    }

    /** Full protocol Task; unlike legacy getStatus(), this never flattens its message/artifacts. */
    public java.util.Map<String, Object> get() throws Exception { return get(10); }
    public java.util.Map<String, Object> get(int timeoutSeconds) throws Exception {
        return network.taskSnapshot(endpoint, taskId, timeoutSeconds);
    }

    public String getTaskId() { return taskId; }
    public Object getResult() { return result; }
    public String getAgentUrl() { return endpoint.url(); }
    public String getTenant() { return endpoint.tenant(); }

    /** Open a fresh SSE subscription for this task, retaining its endpoint and tenant. */
    public TaskEventStream subscribeEvents(int timeoutSeconds) {
        return network.subscribeTask(endpoint, taskId, timeoutSeconds);
    }

    public TaskEventStream subscribeEvents() { return subscribeEvents(30); }

    /**
     * Poll the remote agent for this task's current status.
     *
     * @param timeoutSeconds HTTP timeout
     * @return the task status from the remote agent
     * @throws Exception if the remote call fails
     */
    public Object getStatus(int timeoutSeconds) throws Exception {
        return network.getTaskResult(endpoint, taskId, timeoutSeconds);
    }

    /**
     * Poll the remote agent for this task's current status using the default 10-second timeout.
     */
    public Object getStatus() throws Exception {
        return getStatus(10);
    }

    /**
     * Request cancellation of this task on the remote agent.
     *
     * @param timeoutSeconds HTTP timeout
     * @return the cancellation result from the remote agent
     * @throws Exception if the remote call fails
     */
    public Object cancel(int timeoutSeconds) throws Exception {
        return network.cancel(endpoint, taskId, timeoutSeconds);
    }

    /**
     * Request cancellation of this task on the remote agent using the default 10-second timeout.
     */
    public Object cancel() throws Exception {
        return cancel(10);
    }

    /**
     * Register a per-task push notification webhook for this task on the remote agent.
     *
     * @param webhookUrl     the webhook URL to receive notifications
     * @param token          optional bearer token, or {@code null}
     * @param timeoutSeconds HTTP timeout
     * @return the JSON-RPC result
     * @throws Exception if the remote call fails
     */
    public Object subscribe(String webhookUrl, String token, int timeoutSeconds) throws Exception {
        return network.setPush(endpoint, taskId, webhookUrl, token, timeoutSeconds);
    }

    /**
     * Register a per-task push notification webhook without a bearer token, using the default 10-second timeout.
     */
    public Object subscribe(String webhookUrl) throws Exception {
        return subscribe(webhookUrl, null, 10);
    }

    /**
     * Remove the per-task push notification webhook for this task.
     *
     * @param timeoutSeconds HTTP timeout
     * @return the JSON-RPC result
     * @throws Exception if the remote call fails
     */
    public Object unsubscribe(int timeoutSeconds) throws Exception {
        return network.deletePush(endpoint, taskId, timeoutSeconds);
    }

    /**
     * Remove the per-task push notification webhook using the default 10-second timeout.
     */
    public Object unsubscribe() throws Exception {
        return unsubscribe(10);
    }

    /**
     * Retrieve the push notification config for this task from the remote agent.
     *
     * @param timeoutSeconds HTTP timeout
     * @return the JSON-RPC result containing the push config
     * @throws Exception if the remote call fails
     */
    public Object getPushConfig(int timeoutSeconds) throws Exception {
        return network.getPush(endpoint, taskId, timeoutSeconds);
    }

    /**
     * Retrieve the push notification config using the default 10-second timeout.
     */
    public Object getPushConfig() throws Exception {
        return getPushConfig(10);
    }

    @Override
    public String toString() { return result != null ? result.toString() : "null"; }
}
