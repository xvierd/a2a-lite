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
    private final String agentUrl;
    private final AgentNetwork network;

    public TaskHandle(String taskId, Object result, String agentUrl) {
        this(taskId, result, agentUrl, null);
    }

    public TaskHandle(String taskId, Object result, String agentUrl, AgentNetwork network) {
        this.taskId = taskId;
        this.result = result;
        this.agentUrl = agentUrl;
        this.network = network;
    }

    public String getTaskId() { return taskId; }
    public Object getResult() { return result; }
    public String getAgentUrl() { return agentUrl; }

    /**
     * Poll the remote agent for this task's current status.
     *
     * @param timeoutSeconds HTTP timeout
     * @return the task status from the remote agent
     * @throws Exception if the remote call fails
     */
    public Object getStatus(int timeoutSeconds) throws Exception {
        if (network != null) {
            return network.getRemoteTask(agentUrl, taskId, timeoutSeconds);
        }
        return new AgentNetwork().getRemoteTask(agentUrl, taskId, timeoutSeconds);
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
        if (network != null) {
            return network.cancelRemoteTask(agentUrl, taskId, timeoutSeconds);
        }
        return new AgentNetwork().cancelRemoteTask(agentUrl, taskId, timeoutSeconds);
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
        AgentNetwork net = network != null ? network : new AgentNetwork();
        return net.setTaskPushNotification(agentUrl, taskId, webhookUrl, token, timeoutSeconds);
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
        AgentNetwork net = network != null ? network : new AgentNetwork();
        return net.deleteTaskPushNotification(agentUrl, taskId, timeoutSeconds);
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
        AgentNetwork net = network != null ? network : new AgentNetwork();
        return net.getTaskPushNotification(agentUrl, taskId, timeoutSeconds);
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
