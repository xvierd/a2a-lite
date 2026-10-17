# Message → Task → stream → authenticated → durable

This example uses A2A Lite 1.2.0 and protocol wire version `1.0`.

```sh
# From the repository root:
npm --prefix packages/typescript ci
npm --prefix packages/typescript run build
cd examples/typescript/11_production_path
npm install --package-lock=false
npm run typecheck
npm run learn
```

`npm run learn` runs four local exercises and closes every listener. It needs no database,
external model, callback receiver or credentials beyond the explicit learning keys.

The first call returns a Message. `identify` opts into a Task and proves its `TaskContext.taskId` is
the same task ID returned by the protocol. `count` streams three chunks. The last call
uses a rotating header provider, a stable principal, and explicit tenant membership.

For persistence, install PostgreSQL and use a dedicated development database. Set:

```sh
export A2ALITE_POSTGRES_DSN='postgresql://user:password@localhost/a2alite'
export A2ALITE_CALLBACK_KEY="$(node -e 'console.log(require("crypto").randomBytes(32).toString("base64"))')"
export A2ALITE_API_KEY='choose-a-local-development-key'
DATABASE_URL="$A2ALITE_POSTGRES_DSN" npx a2a-db upgrade
npm run durable -- --migrate
npm run durable
```

Keep the callback encryption key outside the database and retain it across restarts.
The official migration owns protocol tables; the separate Lite migration adds the
version, outbox, execution lease and bounded task journal tables. Neither runs at startup.

Call `steps` using `callRemoteSkillWithHandle(url, 'steps', {}, 5000, { headers:
{ 'X-API-Key': apiKey }, returnImmediately: true })`. Keep its real `taskId`.
A deliberate process crash leaves a nonterminal task until a live replica observes lease expiry.
A saved checkpoint makes it INPUT_REQUIRED; ordinary interrupted work becomes FAILED. Then
call again with the same credentials and `{ taskId: savedTaskId, returnImmediately: true }`.
The explicit checkpoint skill continues from `checkpointData`; completed, canceled and
failed tasks are terminal. Normal skills are not automatically restarted or replayed.

A checkpoint does not make an external side effect atomic. The example's replacement
operation must accept an idempotency key derived from `taskId` and step number, or use
its own transaction before advancing the checkpoint. Try two processes against the same
database to observe scoped GetTask/SubscribeToTask/CancelTask from either replica.
Start the second process with `PORT=8788 npm run durable`, retaining the same database,
API key and callback encryption key in its environment.

The callback outbox guarantees atomic state+enqueue and at-least-once delivery. Receivers
must deduplicate `X-A2A-Delivery-Id`. A database backup includes encrypted callback secrets;
it needs the separately retained encryption key to restore them. This is an opt-in
prototype for durable execution coordination, not a promise that arbitrary code survives
process loss. See [OPERATIONS.md](../../../OPERATIONS.md) for qualification and failure boundaries.
