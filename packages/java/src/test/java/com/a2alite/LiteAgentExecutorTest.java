package com.a2alite;

import com.a2alite.streaming.StreamingHandler;
import org.a2aproject.sdk.server.agentexecution.RequestContext;
import org.a2aproject.sdk.server.events.EventQueue;
import org.a2aproject.sdk.server.events.EventQueueItem;
import org.a2aproject.sdk.server.tasks.AgentEmitter;
import org.a2aproject.sdk.spec.Event;
import org.a2aproject.sdk.spec.Message;
import org.a2aproject.sdk.spec.MessageSendParams;
import org.a2aproject.sdk.spec.TaskStatusUpdateEvent;
import org.a2aproject.sdk.spec.TextPart;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.a2aproject.sdk.spec.TaskState.TASK_STATE_COMPLETED;
import static org.a2aproject.sdk.spec.TaskState.TASK_STATE_SUBMITTED;
import static org.a2aproject.sdk.spec.TaskState.TASK_STATE_WORKING;

class LiteAgentExecutorTest {

    @Test
    void shouldSendMessageUsingOfficialSdkEmitter() {
        var agent = Agent.builder().name("SDKBot").description("SDK compatibility").build();
        agent.skill("greet", params -> "Hello, " + params.get("name") + "!");
        var context = requestContext("{\"skill\":\"greet\",\"params\":{\"name\":\"World\"}}");
        var queue = new RecordingQueue();

        agent.getExecutor().execute(context, new AgentEmitter(context, queue));

        assertThat(queue.events).hasSize(1);
        var message = (Message) queue.events.get(0);
        assertThat(message.role()).isEqualTo(Message.Role.ROLE_AGENT);
        assertThat(message.contextId()).isEqualTo(context.getContextId());
        assertThat(message.messageId()).isNotBlank();
        assertThat(((TextPart) message.parts().get(0)).text()).isEqualTo("Hello, World!");
    }

    @Test
    void shouldStreamTaskLifecycleUsingOfficialSdkEmitter() {
        var agent = Agent.builder().name("SDKBot").description("SDK compatibility").build();
        agent.skill("stream", SkillConfig.withStreaming(),
            params -> StreamingHandler.fromIterator(List.of("Hello ", "World").iterator()));
        var context = requestContext("{\"skill\":\"stream\"}");
        var queue = new RecordingQueue();

        agent.getExecutor().execute(context, new AgentEmitter(context, queue));

        assertThat(queue.events.get(0)).isInstanceOf(org.a2aproject.sdk.spec.Task.class);
        var initial = (org.a2aproject.sdk.spec.Task) queue.events.get(0);
        assertThat(initial.status().state()).isEqualTo(TASK_STATE_SUBMITTED);
        assertThat(initial.id()).isEqualTo(context.getTaskId());
        var updates = queue.events.stream().skip(1).map(TaskStatusUpdateEvent.class::cast).toList();
        assertThat(updates).extracting(update -> update.status().state()).containsExactly(
            TASK_STATE_WORKING, TASK_STATE_WORKING,
            TASK_STATE_WORKING, TASK_STATE_COMPLETED);
        assertThat(updates).allSatisfy(update -> {
            assertThat(update.taskId()).isEqualTo(context.getTaskId());
            assertThat(update.contextId()).isEqualTo(context.getContextId());
        });
        assertThat(((TextPart) updates.get(1).status().message().parts().get(0)).text())
            .isEqualTo("Hello ");
        assertThat(((TextPart) updates.get(2).status().message().parts().get(0)).text())
            .isEqualTo("World");
    }

    private RequestContext requestContext(String text) {
        var message = Message.builder()
            .messageId("request-1")
            .role(Message.Role.ROLE_USER)
            .parts(new TextPart(text))
            .build();
        return new RequestContext.Builder()
            .setParams(MessageSendParams.builder().message(message).build())
            .build();
    }

    // Capture events from the real SDK emitter without starting a transport or event bus.
    private static class RecordingQueue extends EventQueue {
        private final List<Event> events = new ArrayList<>();

        @Override
        public void enqueueItem(EventQueueItem item) {
            events.add(item.getEvent());
        }

        @Override
        public int size() {
            return events.size();
        }

        @Override
        public EventQueue tap() {
            throw new UnsupportedOperationException();
        }

        @Override
        public EventQueueItem dequeueEventItem(int waitMilliSeconds) {
            throw new UnsupportedOperationException();
        }

        @Override
        public void awaitQueuePollerStart() {}

        @Override
        public void signalQueuePollerStarted() {}

        @Override
        public void close() {}

        @Override
        public void close(boolean immediate) {}

        @Override
        public void close(boolean immediate, boolean notifyParent) {}
    }
}
