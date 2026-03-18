package com.a2alite.push;

import java.util.Map;

/**
 * Interface for push notification delivery after a skill completes.
 *
 * <p>Implementations can send events via HTTP webhooks, logging,
 * message queues, or any other mechanism.
 *
 * <pre>{@code
 * PushNotifier notifier = new LogPushNotifier();
 * agent.onComplete((skill, result) -> notifier.notify(Map.of(
 *     "skill", skill,
 *     "result", result
 * )));
 * }</pre>
 */
public interface PushNotifier {

    /**
     * Deliver a push notification event.
     *
     * @param event the event payload, typically containing skill name and result
     * @throws PushNotifierException if delivery fails and the implementation does not retry
     */
    void notify(Map<String, Object> event);
}
