package com.a2alite.server;

import org.a2aproject.sdk.jsonrpc.common.json.JsonUtil;
import org.a2aproject.sdk.server.tasks.PushNotificationSender;
import org.a2aproject.sdk.spec.ListTaskPushNotificationConfigsParams;
import org.a2aproject.sdk.spec.Message;
import org.a2aproject.sdk.spec.StreamingEventKind;
import org.a2aproject.sdk.spec.Task;
import org.a2aproject.sdk.spec.TaskArtifactUpdateEvent;
import org.a2aproject.sdk.spec.TaskStatusUpdateEvent;

import java.io.IOException;
import java.util.HashMap;
import java.util.Map;
import java.util.logging.Logger;

final class SdkPushSender {
    private static final Logger LOG = Logger.getLogger(SdkPushSender.class.getName());

    @FunctionalInterface
    interface Delivery {
        void post(String url, String payload, Map<String, String> headers) throws IOException;
    }

    static PushNotificationSender forBackend(ProtocolBackend backend, Delivery delivery) {
        // The SDK calls the sender after persistence succeeds. With an atomic outbox
        // this acknowledges the handoff. Only the outbox worker acknowledges HTTP delivery.
        if (backend.durableNotifications()) return (event, task) -> true;
        var configs = backend.pushConfigs();
        return (event, task) -> {
            String taskId = taskId(event);
            if (taskId == null || taskId.isEmpty()) return true; // Standalone message.
            boolean success = true;
            String token = "";
            do {
                var page = configs.getInfo(new ListTaskPushNotificationConfigsParams(taskId, 100, token, ""));
                for (var config : page.configs()) {
                    try {
                        var headers = new HashMap<String, String>();
                        if (config.token() != null) headers.put("X-A2A-Notification-Token", config.token());
                        var auth = config.authentication();
                        if (auth != null && auth.credentials() != null)
                            headers.put("Authorization", auth.scheme() + " " + auth.credentials());
                        delivery.post(config.url(), JsonUtil.toJsonStreamingEvent(event), headers);
                    } catch (Exception failure) {
                        success = false;
                        LOG.warning("Task callback delivery failed: " + failure.getClass().getSimpleName());
                    }
                }
                token = page.nextPageToken();
            } while (token != null && !token.isEmpty());
            return success;
        };
    }

    // V1 push addresses the event's task. The SDK's separate task snapshot is optional.
    private static String taskId(StreamingEventKind event) {
        if (event instanceof Task task) return task.id();
        if (event instanceof Message message) return message.taskId();
        if (event instanceof TaskStatusUpdateEvent status) return status.taskId();
        if (event instanceof TaskArtifactUpdateEvent artifact) return artifact.taskId();
        throw new IllegalArgumentException("Unsupported push event");
    }
}
