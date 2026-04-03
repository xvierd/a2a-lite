package com.a2alite;

import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class TaskHandleTest {

    @Test
    void testTaskHandleFields() {
        var handle = new TaskHandle("task-123", Map.of("key", "value"), "http://localhost:8787");

        assertThat(handle.getTaskId()).isEqualTo("task-123");
        assertThat(handle.getResult()).isEqualTo(Map.of("key", "value"));
        assertThat(handle.getAgentUrl()).isEqualTo("http://localhost:8787");
    }

    @Test
    void testTaskHandleToString() {
        var handle = new TaskHandle("task-1", "hello world", "http://localhost:8787");
        assertThat(handle.toString()).isEqualTo("hello world");
    }

    @Test
    void testTaskHandleToStringWithMap() {
        var result = Map.of("status", "ok");
        var handle = new TaskHandle("task-2", result, "http://agent:9000");
        assertThat(handle.toString()).isEqualTo(result.toString());
    }

    @Test
    void testTaskHandleNullResult() {
        var handle = new TaskHandle("task-3", null, "http://localhost:8787");
        assertThat(handle.toString()).isEqualTo("null");
        assertThat(handle.getResult()).isNull();
    }

    @Test
    void testTaskHandleNullTaskId() {
        var handle = new TaskHandle(null, "result", "http://localhost:8787");
        assertThat(handle.getTaskId()).isNull();
        assertThat(handle.getResult()).isEqualTo("result");
    }
}
