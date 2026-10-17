import assert from "node:assert/strict";
import {
  Agent,
  APIKeyAuth,
  TaskContext,
  callRemoteSkill,
  callRemoteSkillWithHandle,
  streamRemoteSkill,
} from "a2a-lite";

const agent = new Agent({
  name: "Learning",
  description: "Message, Task and stream",
});
agent.skill("hello", async ({ name }) => `Hello, ${name}!`);
agent.skill("identify", { task: true, taskContext: true }, async ({ task }) => {
  const context = task as TaskContext;
  await context.update("working", "Keeping the protocol task ID", 0.5);
  return context.taskId;
});
agent.skill("count", { streaming: true }, async function* () {
  yield "one";
  yield "two";
  yield "three";
});
const runtime = await agent.start({ host: "127.0.0.1", port: 0 });
try {
  console.log(await callRemoteSkill(runtime.url, "hello", { name: "A2A" }));
  const task = await callRemoteSkillWithHandle(runtime.url, "identify", {});
  assert.equal(task.result, task.taskId);
  console.log("One real task ID:", task.taskId, await task.get());
  for await (const chunk of streamRemoteSkill(runtime.url, "count", {}))
    console.log("Stream:", chunk);
} finally {
  await runtime.stop();
}

const secure = new Agent({
  name: "Authenticated",
  description: "Stable identity after rotation",
  profile: "authenticated",
  auth: new APIKeyAuth({
    identities: {
      "learning-key": {
        userId: "student",
        namespace: "course",
        authorizedTenants: ["classroom"],
      },
      "rotated-learning-key": {
        userId: "student",
        namespace: "course",
        authorizedTenants: ["classroom"],
      },
    },
  }),
});
secure.skill("hello", async () => "Authenticated classroom");
const secureRuntime = await secure.start({ host: "127.0.0.1", port: 0 });
try {
  console.log(
    await callRemoteSkill(secureRuntime.url, "hello", {}, 5000, {
      tenant: "classroom",
      credentialProvider: () => ({ "X-API-Key": "rotated-learning-key" }),
    }),
  );
} finally {
  await secureRuntime.stop();
}
