package com.a2alite.push;

import java.util.Map;

/**
 * Abstract interface for push notification delivery.
 *
 * <p>Implement this interface to send A2A skill completion events to external
 * systems such as webhooks, message queues, Slack, PagerDuty, etc.
 *
 * <p>Example custom implementation:
 * <pre>{@code
 * public class SlackPushNotifier implements PushNotifier {
 *     private final String webhookUrl;
 *
 *     public SlackPushNotifier(String webhookUrl) {
 *         this.webhookUrl = webhookUrl;
 *     }
 *
 *     @Override
 *     public void notify(Map<String, Object> event) {
 *         String text = "Skill `" + event.get("skill") + "` completed";
 *         // POST to Slack webhook...
 *     }
 * }
 * }</pre>
 *
 * <p>Usage:
 * <pre>{@code
 * Agent agent = Agent.builder()
 *     .name("Bot")
 *     .description("...")
 *     .pushNotifier(new WebhookPushNotifier("https://my-app.com/webhook"))
 *     .build();
 * }</pre>
 */
public interface PushNotifier {

    /**
     * Send a notification for a skill completion event.
     *
     * @param event Map containing:
     *              <ul>
     *              <li>{@code skill} (String) - the skill that completed</li>
     *              <li>{@code result} (Object) - the skill's return value</li>
     *              <li>{@code status} (String) - "completed" or "failed"</li>
     *              <li>{@code timestamp} (long) - Unix timestamp in milliseconds</li>
     *              <li>{@code agent} (String) - the agent name</li>
     *              </ul>
     */
    void notify(Map<String, Object> event);
}
