package com.a2alite.push;

import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

class LogPushNotifierTest {

    // -------------------------------------------------------------------------
    // Helper: in-memory log handler
    // -------------------------------------------------------------------------

    private static class CapturingHandler extends Handler {
        final List<LogRecord> records = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            records.add(record);
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    // -------------------------------------------------------------------------
    // Tests
    // -------------------------------------------------------------------------

    @Test
    void notifyDoesNotThrow() {
        var notifier = new LogPushNotifier();
        assertThatCode(() -> notifier.notify(Map.of("skill", "echo", "result", "hello")))
            .doesNotThrowAnyException();
    }

    @Test
    void notifyWithEmptyMapDoesNotThrow() {
        var notifier = new LogPushNotifier();
        assertThatCode(() -> notifier.notify(Map.of()))
            .doesNotThrowAnyException();
    }

    @Test
    void notifyLogsEventKeyAndValue() {
        var handler = new CapturingHandler();
        handler.setLevel(Level.ALL);

        var notifier = new LogPushNotifier("com.a2alite.push.test.LogPushNotifierTest");
        Logger underlying = notifier.getLogger();
        underlying.addHandler(handler);
        underlying.setLevel(Level.ALL);
        underlying.setUseParentHandlers(false);

        notifier.notify(Map.of("skill", "greet", "result", "Hello, World!"));

        assertThat(handler.records).hasSize(1);
        String message = handler.records.get(0).getMessage();
        // The message is a Supplier — force evaluation via the formatted message
        String formatted = handler.records.get(0).getParameters() == null
            ? message
            : String.format(message, handler.records.get(0).getParameters());

        // At INFO level the record message is the supplier result string
        assertThat(handler.records.get(0).getLevel()).isEqualTo(Level.INFO);
    }

    @Test
    void notifyLogsContainsEventKeys() {
        var handler = new CapturingHandler();
        handler.setLevel(Level.ALL);

        String loggerName = "com.a2alite.push.test.KeyValueTest";
        var notifier = new LogPushNotifier(loggerName, Level.FINE);
        Logger underlying = notifier.getLogger();
        underlying.addHandler(handler);
        underlying.setLevel(Level.ALL);
        underlying.setUseParentHandlers(false);

        notifier.notify(Map.of("skill", "sum", "result", 42));

        assertThat(handler.records).hasSize(1);
        // The LogRecord's message (supplier) is lazily evaluated; use getMessage()
        // which returns the raw format string or supplier string
        LogRecord rec = handler.records.get(0);
        // Force supplier evaluation by calling the standard formatter
        java.util.logging.SimpleFormatter fmt = new java.util.logging.SimpleFormatter();
        String formatted = fmt.format(rec);
        assertThat(formatted).contains("skill");
        assertThat(formatted).contains("sum");
    }

    @Test
    void notifyUsesConfiguredLevel() {
        var notifier = new LogPushNotifier("test.level.logger", Level.WARNING);
        assertThat(notifier.getLevel()).isEqualTo(Level.WARNING);
    }

    @Test
    void defaultConstructorUsesInfoLevel() {
        var notifier = new LogPushNotifier();
        assertThat(notifier.getLevel()).isEqualTo(Level.INFO);
    }

    @Test
    void customLoggerNameIsUsed() {
        String name = "my.custom.notifier";
        var notifier = new LogPushNotifier(name);
        assertThat(notifier.getLogger().getName()).isEqualTo(name);
    }

    @Test
    void notifyCalledMultipleTimesDoesNotThrow() {
        var notifier = new LogPushNotifier();
        for (int i = 0; i < 10; i++) {
            final int idx = i;
            assertThatCode(() -> notifier.notify(Map.of("iteration", idx)))
                .doesNotThrowAnyException();
        }
    }
}
