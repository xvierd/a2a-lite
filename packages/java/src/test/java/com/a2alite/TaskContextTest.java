package com.a2alite;

import com.a2alite.tasks.*;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

class TaskContextTest {

    // === TaskState Tests ===

    @Test
    void shouldParseTaskStatesFromString() {
        assertThat(TaskState.fromString("submitted")).isEqualTo(TaskState.SUBMITTED);
        assertThat(TaskState.fromString("working")).isEqualTo(TaskState.WORKING);
        assertThat(TaskState.fromString("completed")).isEqualTo(TaskState.COMPLETED);
        assertThat(TaskState.fromString("failed")).isEqualTo(TaskState.FAILED);
        assertThat(TaskState.fromString("canceled")).isEqualTo(TaskState.CANCELED);
        assertThat(TaskState.fromString("input-required")).isEqualTo(TaskState.INPUT_REQUIRED);
    }

    @Test
    void shouldConvertTaskStateToString() {
        assertThat(TaskState.SUBMITTED.getValue()).isEqualTo("submitted");
        assertThat(TaskState.WORKING.getValue()).isEqualTo("working");
        assertThat(TaskState.COMPLETED.getValue()).isEqualTo("completed");
    }

    // === Task Tests ===

    @Test
    void shouldCreateTask() {
        var task = new Task("test-id", "mySkill", Map.of("key", "value"));
        assertThat(task.getId()).isEqualTo("test-id");
        assertThat(task.getSkill()).isEqualTo("mySkill");
        assertThat(task.getParams()).containsEntry("key", "value");
        assertThat(task.getStatus().state()).isEqualTo(TaskState.SUBMITTED);
        assertThat(task.getHistory()).isEmpty();
    }

    @Test
    void shouldUpdateTaskStatus() {
        var task = new Task("id", "skill", Map.of());
        task.updateStatus(TaskState.WORKING, "Processing...", 0.5);

        assertThat(task.getStatus().state()).isEqualTo(TaskState.WORKING);
        assertThat(task.getStatus().message()).isEqualTo("Processing...");
        assertThat(task.getStatus().progress()).isEqualTo(0.5);
        assertThat(task.getHistory()).hasSize(1);
        assertThat(task.getHistory().get(0).state()).isEqualTo(TaskState.SUBMITTED);
    }

    @Test
    void shouldTrackMultipleStatusUpdates() {
        var task = new Task("id", "skill", Map.of());
        task.updateStatus(TaskState.WORKING, "Step 1", 0.25);
        task.updateStatus(TaskState.WORKING, "Step 2", 0.50);
        task.updateStatus(TaskState.COMPLETED, "Done", 1.0);

        assertThat(task.getHistory()).hasSize(3);
        assertThat(task.getStatus().state()).isEqualTo(TaskState.COMPLETED);
    }

    // === TaskContext Tests ===

    @Test
    void shouldGetTaskId() {
        var task = new Task("ctx-id", "skill", Map.of());
        var ctx = new TaskContext(task);
        assertThat(ctx.getTaskId()).isEqualTo("ctx-id");
    }

    @Test
    void shouldGetState() {
        var task = new Task("id", "skill", Map.of());
        var ctx = new TaskContext(task);
        assertThat(ctx.getState()).isEqualTo(TaskState.SUBMITTED);
    }

    @Test
    void shouldUpdateViaContext() {
        var task = new Task("id", "skill", Map.of());
        var ctx = new TaskContext(task);

        ctx.update(TaskState.WORKING, "Working...", 0.5);
        assertThat(ctx.getState()).isEqualTo(TaskState.WORKING);
        assertThat(task.getStatus().message()).isEqualTo("Working...");
        assertThat(task.getStatus().progress()).isEqualTo(0.5);
    }

    @Test
    void shouldComplete() {
        var task = new Task("id", "skill", Map.of());
        var ctx = new TaskContext(task);

        ctx.complete("All done!");
        assertThat(ctx.getState()).isEqualTo(TaskState.COMPLETED);
        assertThat(task.getStatus().progress()).isEqualTo(1.0);
    }

    @Test
    void shouldCompleteWithNoMessage() {
        var task = new Task("id", "skill", Map.of());
        var ctx = new TaskContext(task);

        ctx.complete();
        assertThat(ctx.getState()).isEqualTo(TaskState.COMPLETED);
    }

    @Test
    void shouldFail() {
        var task = new Task("id", "skill", Map.of());
        var ctx = new TaskContext(task);

        ctx.fail("Something broke");
        assertThat(ctx.getState()).isEqualTo(TaskState.FAILED);
        assertThat(task.getStatus().message()).isEqualTo("Something broke");
    }

    @Test
    void shouldNotifyStatusCallbacks() {
        var task = new Task("id", "skill", Map.of());
        var ctx = new TaskContext(task);

        List<TaskState> states = new ArrayList<>();
        ctx.onStatusChange(status -> states.add(status.state()));

        ctx.update(TaskState.WORKING, "Working", null);
        ctx.complete("Done");

        assertThat(states).containsExactly(TaskState.WORKING, TaskState.COMPLETED);
    }

    @Test
    void shouldHandleCallbackErrors() {
        var task = new Task("id", "skill", Map.of());
        var ctx = new TaskContext(task);

        ctx.onStatusChange(status -> {
            throw new RuntimeException("callback error");
        });

        // Should not throw
        ctx.update(TaskState.WORKING, "test", null);
        assertThat(ctx.getState()).isEqualTo(TaskState.WORKING);
    }

    @Test
    void shouldSupportMultipleCallbacks() {
        var task = new Task("id", "skill", Map.of());
        var ctx = new TaskContext(task);

        List<String> log = new ArrayList<>();
        ctx.onStatusChange(s -> log.add("cb1:" + s.state().getValue()));
        ctx.onStatusChange(s -> log.add("cb2:" + s.state().getValue()));

        ctx.update(TaskState.WORKING, "test", null);
        assertThat(log).containsExactly("cb1:working", "cb2:working");
    }

    // === InMemoryTaskStore Tests ===

    @Test
    void shouldCreateAndGetTask() {
        var store = new InMemoryTaskStore();
        var task = store.create("greet", Map.of("name", "World"));

        assertThat(task.getId()).isNotNull();
        assertThat(task.getSkill()).isEqualTo("greet");

        var found = store.get(task.getId());
        assertThat(found).isPresent();
        assertThat(found.get().getId()).isEqualTo(task.getId());
    }

    @Test
    void shouldReturnEmptyForMissingTask() {
        var store = new InMemoryTaskStore();
        assertThat(store.get("nonexistent")).isEmpty();
    }

    @Test
    void shouldDeleteTask() {
        var store = new InMemoryTaskStore();
        var task = store.create("skill", Map.of());

        assertThat(store.delete(task.getId())).isTrue();
        assertThat(store.get(task.getId())).isEmpty();
    }

    @Test
    void shouldReturnFalseForDeletingNonexistent() {
        var store = new InMemoryTaskStore();
        assertThat(store.delete("nonexistent")).isFalse();
    }

    @Test
    void shouldListAllTasks() {
        var store = new InMemoryTaskStore();
        store.create("skill1", Map.of());
        store.create("skill2", Map.of());
        store.create("skill3", Map.of());

        var tasks = store.list();
        assertThat(tasks).hasSize(3);
    }

    @Test
    void shouldFilterBySkill() {
        var store = new InMemoryTaskStore();
        store.create("greet", Map.of());
        store.create("greet", Map.of());
        store.create("farewell", Map.of());

        var tasks = store.list("greet", null, 100);
        assertThat(tasks).hasSize(2);
    }

    @Test
    void shouldFilterByState() {
        var store = new InMemoryTaskStore();
        var t1 = store.create("skill", Map.of());
        var t2 = store.create("skill", Map.of());
        t1.updateStatus(TaskState.COMPLETED, "done", 1.0);
        store.update(t1);

        var completed = store.list(null, TaskState.COMPLETED, 100);
        assertThat(completed).hasSize(1);
        assertThat(completed.get(0).getId()).isEqualTo(t1.getId());
    }

    @Test
    void shouldLimitResults() {
        var store = new InMemoryTaskStore();
        for (int i = 0; i < 10; i++) {
            store.create("skill", Map.of());
        }

        var tasks = store.list(null, null, 5);
        assertThat(tasks).hasSize(5);
    }

    @Test
    void shouldClearStore() {
        var store = new InMemoryTaskStore();
        store.create("skill", Map.of());
        store.create("skill", Map.of());

        store.clear();
        assertThat(store.size()).isEqualTo(0);
        assertThat(store.list()).isEmpty();
    }

    @Test
    void shouldBeThreadSafe() throws InterruptedException {
        var store = new InMemoryTaskStore();
        int threadCount = 10;
        var latch = new CountDownLatch(threadCount);

        for (int i = 0; i < threadCount; i++) {
            final int idx = i;
            new Thread(() -> {
                store.create("skill" + idx, Map.of("index", idx));
                latch.countDown();
            }).start();
        }

        latch.await(5, TimeUnit.SECONDS);
        assertThat(store.size()).isEqualTo(threadCount);
    }

    // === TaskStatus Tests ===

    @Test
    void shouldCreateStatusWithDefaults() {
        var status = new TaskStatus(TaskState.SUBMITTED);
        assertThat(status.state()).isEqualTo(TaskState.SUBMITTED);
        assertThat(status.message()).isNull();
        assertThat(status.progress()).isNull();
        assertThat(status.timestamp()).isNotNull();
    }

    @Test
    void shouldCreateStatusWithMessage() {
        var status = new TaskStatus(TaskState.WORKING, "Processing");
        assertThat(status.getMessage()).isPresent().contains("Processing");
    }

    @Test
    void shouldCreateStatusWithProgress() {
        var status = new TaskStatus(TaskState.WORKING, "Half done", 0.5);
        assertThat(status.getProgress()).isPresent().contains(0.5);
    }

    @Test
    void shouldConvertToMap() {
        var status = new TaskStatus(TaskState.WORKING, "test", 0.5);
        var map = status.toMap();
        assertThat(map.get("state")).isEqualTo("working");
    }
}
