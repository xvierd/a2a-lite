package com.a2alite.push;

import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * A {@link PushNotifier} that logs events via {@code java.util.logging}.
 *
 * <p>Useful during development so you can see notifications without configuring
 * a real webhook endpoint.
 *
 * <pre>{@code
 * PushNotifier notifier = new LogPushNotifier();
 * // or with a custom logger name:
 * PushNotifier notifier = new LogPushNotifier("my.app.events");
 * }</pre>
 */
public class LogPushNotifier implements PushNotifier {

    private final Logger logger;
    private final Level level;

    /**
     * Create a notifier that logs at INFO level using the class logger.
     */
    public LogPushNotifier() {
        this(LogPushNotifier.class.getName(), Level.INFO);
    }

    /**
     * Create a notifier with a custom logger name and INFO level.
     *
     * @param loggerName the name passed to {@link Logger#getLogger(String)}
     */
    public LogPushNotifier(String loggerName) {
        this(loggerName, Level.INFO);
    }

    /**
     * Create a notifier with a custom logger name and log level.
     *
     * @param loggerName the name passed to {@link Logger#getLogger(String)}
     * @param level      the log level to use when emitting events
     */
    public LogPushNotifier(String loggerName, Level level) {
        this.logger = Logger.getLogger(loggerName);
        this.level = level;
    }

    /**
     * Log the event. Never throws.
     *
     * @param event the event payload
     */
    @Override
    public void notify(Map<String, Object> event) {
        logger.log(level, () -> buildMessage(event));
    }

    private String buildMessage(Map<String, Object> event) {
        var sb = new StringBuilder("[PushNotifier] event={");
        boolean first = true;
        for (Map.Entry<String, Object> entry : event.entrySet()) {
            if (!first) sb.append(", ");
            sb.append(entry.getKey()).append('=').append(entry.getValue());
            first = false;
        }
        sb.append('}');
        return sb.toString();
    }

    /**
     * Return the underlying logger (useful for testing).
     */
    public Logger getLogger() {
        return logger;
    }

    /**
     * Return the log level used for events.
     */
    public Level getLevel() {
        return level;
    }
}
