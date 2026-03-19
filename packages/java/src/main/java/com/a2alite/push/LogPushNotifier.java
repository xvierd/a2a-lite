package com.a2alite.push;

import java.util.Map;
import java.util.logging.Level;
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

    private final Logger logger;
    private final Level level;

    /** Creates a notifier using the class logger at INFO level. */
    public LogPushNotifier() {
        this(LogPushNotifier.class.getName(), Level.INFO);
    }

    /** Creates a notifier using a custom logger name at INFO level. */
    public LogPushNotifier(String loggerName) {
        this(loggerName, Level.INFO);
    }

    /** Creates a notifier using a custom logger name and log level. */
    public LogPushNotifier(String loggerName, Level level) {
        this.logger = Logger.getLogger(loggerName);
        this.level = level;
    }

    /** Returns the log level used for events. */
    public Level getLevel() {
        return level;
    }

    /** Returns the underlying logger. */
    public Logger getLogger() {
        return logger;
    }

    @Override
    public void notify(Map<String, Object> event) {
        logger.log(level, String.format("[A2A Push] skill=%s status=%s agent=%s timestamp=%s",
                event.get("skill"),
                event.get("status"),
                event.get("agent"),
                event.get("timestamp")));
    }
}
