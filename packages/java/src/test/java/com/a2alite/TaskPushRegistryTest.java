package com.a2alite;

import com.a2alite.push.TaskPushRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class TaskPushRegistryTest {

    @Test
    void testSet_and_get() {
        var registry = new TaskPushRegistry();
        registry.set("task-1", "http://example.com/hook", "my-token");

        var config = registry.get("task-1");
        assertThat(config).isPresent();
        assertThat(config.get().url()).isEqualTo("http://example.com/hook");
        assertThat(config.get().token()).isEqualTo("my-token");
    }

    @Test
    void testSet_and_get_withoutToken() {
        var registry = new TaskPushRegistry();
        registry.set("task-2", "http://example.com/hook");

        var config = registry.get("task-2");
        assertThat(config).isPresent();
        assertThat(config.get().url()).isEqualTo("http://example.com/hook");
        assertThat(config.get().token()).isNull();
    }

    @Test
    void testGet_missing() {
        var registry = new TaskPushRegistry();

        var config = registry.get("nonexistent");
        assertThat(config).isEmpty();
    }

    @Test
    void testDelete() {
        var registry = new TaskPushRegistry();
        registry.set("task-3", "http://example.com/hook");

        boolean removed = registry.delete("task-3");
        assertThat(removed).isTrue();
        assertThat(registry.get("task-3")).isEmpty();
    }

    @Test
    void testDelete_missing() {
        var registry = new TaskPushRegistry();

        boolean removed = registry.delete("nonexistent");
        assertThat(removed).isFalse();
    }

    @Test
    void testContains() {
        var registry = new TaskPushRegistry();

        assertThat(registry.contains("task-4")).isFalse();

        registry.set("task-4", "http://example.com/hook");
        assertThat(registry.contains("task-4")).isTrue();

        registry.delete("task-4");
        assertThat(registry.contains("task-4")).isFalse();
    }
}
