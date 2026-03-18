package com.a2alite.push;

import java.util.Map;
import java.util.logging.Logger;

/**
 * Development push notifier that logs events to Java's standard logger.
 * Useful for testing push notification wiring without a real endpoint.
 *
 * <p>Example:
 * <pre>{@code
 * Agent agent = Agent.builder()
 *     .name("Bot")
 *     .description("...")
 *     .pushNotifier(new LogPushNotifier())
 *     .build();
 * }</pre>
 */
public class LogPushNotifier implements PushNotifier {

    private static final Logger logger = Logger.getLogger(LogPushNotifier.class.getName());

    @Override
    public void notify(Map<String, Object> event) {
        logger.info(String.format("[A2A Push] skill=%s status=%s agent=%s timestamp=%s",
                event.get("skill"),
                event.get("status"),
                event.get("agent"),
                event.get("timestamp")));
    }
}
