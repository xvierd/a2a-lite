import {
  Agent,
  APIKeyAuth,
  TaskContext,
  createPostgresPersistence,
  migratePostgresRuntime,
} from "a2a-lite";

const connectionString = process.env.A2ALITE_POSTGRES_DSN;
const encryptionKey = process.env.A2ALITE_CALLBACK_KEY;
const apiKey = process.env.A2ALITE_API_KEY;
if (!connectionString || !encryptionKey || !apiKey)
  throw new Error(
    "Set A2ALITE_POSTGRES_DSN, A2ALITE_CALLBACK_KEY (base64 32 bytes), and A2ALITE_API_KEY",
  );
if (process.argv.includes("--migrate")) {
  // Apply the official SDK migration first: DATABASE_URL="$A2ALITE_POSTGRES_DSN" npx a2a-db upgrade
  await migratePostgresRuntime({ connectionString });
} else {
  const persistence = await createPostgresPersistence({
    connectionString,
    encryptionKey,
    delivery: {},
    execution: {},
  });
  const agent = new Agent({
    name: "Durable",
    description: "Explicit resumable checkpoints",
    profile: "durable",
    persistence,
    auth: new APIKeyAuth({ identities: { [apiKey]: "student" } }),
  });
  agent.skill(
    "steps",
    { task: true, taskContext: true, checkpoint: true },
    async ({ task }) => {
      const context = task as TaskContext;
      const saved = context.checkpointData as { next: number } | null;
      for (let index = saved?.next ?? 0; index < 10; index++) {
        context.signal.throwIfAborted();
        // Replace this delay only with an idempotent operation keyed by taskId+index.
        await new Promise((resolve) => setTimeout(resolve, 250));
        await context.checkpoint({ next: index + 1 });
        await context.update("working", `Step ${index + 1}`, (index + 1) / 10);
      }
      return { taskId: context.taskId, completed: 10 };
    },
  );
  const runtime = await agent.start({
    host: "127.0.0.1",
    port: Number(process.env.PORT ?? 8787),
  });
  console.log(`Durable agent: ${runtime.url}`);
  for (const signal of ["SIGINT", "SIGTERM"] as const)
    process.once(signal, () => {
      void runtime.stop();
    });
}
