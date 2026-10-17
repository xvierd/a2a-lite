"""Lease-fenced recovery for explicitly restartable skills.

A recoverable handler runs again from its beginning. Use checkpoints and
transactional effects; arbitrary external effects require receiver idempotency.
"""

from __future__ import annotations

import asyncio
import base64
import json
from uuid import uuid4

FENCE_KEY = "a2a-lite.execution-fence"
EXECUTION_KEY = "a2a_lite.execution"
CANCEL_KEY = "a2a_lite.authorized_cancel"
CANCEL_FENCE = "a2a-lite.authorized-cancel"
TERMINAL = {"TASK_STATE_COMPLETED", "TASK_STATE_FAILED", "TASK_STATE_CANCELED", "TASK_STATE_REJECTED"}
INTERRUPTED = {"TASK_STATE_INPUT_REQUIRED", "TASK_STATE_AUTH_REQUIRED"}


class ExecutionLeaseLostError(Exception):
    """This execution no longer owns its durable task."""


def add_tables(backend):
    from sqlalchemy import Boolean, Column, Float, Integer, LargeBinary, String, Table

    backend.executions = Table(
        "a2a_lite_executions",
        backend.metadata,
        Column("task_id", String(36), primary_key=True),
        Column("owner", String(255), nullable=False),
        Column("fence", String(36), nullable=False),
        Column("lease_until", Float, nullable=False),
        Column("status", String(16), nullable=False),
        Column("recoverable", Boolean, nullable=False),
        Column("request_data", LargeBinary, nullable=False),
        Column("checkpoint", LargeBinary),
        Column("recovery_attempts", Integer, nullable=False, server_default="0"),
    )
    backend.effects = Table(
        "a2a_lite_effects",
        backend.metadata,
        Column("task_id", String(36), primary_key=True),
        Column("effect_key", String(255), primary_key=True),
        Column("result", LargeBinary, nullable=False),
    )


async def migrate_fences(conn, backend):
    from sqlalchemy import text

    if backend.engine.dialect.name == "postgresql":
        await conn.execute(
            text("""CREATE OR REPLACE FUNCTION a2a_lite_execution_fence() RETURNS trigger AS $$
        DECLARE lease a2a_lite_executions%ROWTYPE;
        BEGIN
          SELECT * INTO lease FROM a2a_lite_executions WHERE task_id=NEW.id FOR UPDATE;
          IF FOUND AND (NEW.status->>'state' <> 'TASK_STATE_CANCELED' OR
             NEW.metadata->>'a2a-lite.execution-fence' IS DISTINCT FROM 'a2a-lite.authorized-cancel') THEN
            IF NEW.metadata->>'a2a-lite.execution-fence' IS DISTINCT FROM lease.fence OR
               lease.status <> 'running' OR lease.lease_until <= EXTRACT(EPOCH FROM clock_timestamp()) THEN
              RAISE EXCEPTION 'Execution lease lost';
            END IF;
          END IF;
          IF FOUND AND NEW.status->>'state' IN ('TASK_STATE_COMPLETED','TASK_STATE_FAILED','TASK_STATE_CANCELED','TASK_STATE_REJECTED') THEN
            UPDATE a2a_lite_executions SET status='done' WHERE task_id=NEW.id;
          ELSIF FOUND AND NEW.status->>'state' IN ('TASK_STATE_INPUT_REQUIRED','TASK_STATE_AUTH_REQUIRED') THEN
            UPDATE a2a_lite_executions SET status='paused' WHERE task_id=NEW.id;
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
        )
        await conn.execute(text("DROP TRIGGER IF EXISTS a2a_lite_execution_write ON tasks"))
        await conn.execute(
            text("""CREATE TRIGGER a2a_lite_execution_write BEFORE INSERT OR UPDATE ON tasks
            FOR EACH ROW EXECUTE FUNCTION a2a_lite_execution_fence()""")
        )
    else:
        for operation in ("INSERT", "UPDATE"):
            await conn.execute(text(f"DROP TRIGGER IF EXISTS a2a_lite_execution_{operation.lower()}"))
            await conn.execute(
                text(f"""CREATE TRIGGER a2a_lite_execution_{operation.lower()} BEFORE {operation} ON tasks
            WHEN EXISTS (SELECT 1 FROM a2a_lite_executions WHERE task_id=NEW.id)
            BEGIN
              SELECT CASE WHEN (json_extract(NEW.status, '$.state') <> 'TASK_STATE_CANCELED' OR
                json_extract(NEW.metadata, '$."a2a-lite.execution-fence"') IS NOT 'a2a-lite.authorized-cancel')
                AND EXISTS (SELECT 1 FROM a2a_lite_executions WHERE task_id=NEW.id AND
                  (status <> 'running' OR json_extract(NEW.metadata, '$."a2a-lite.execution-fence"') IS NOT fence OR
                   lease_until <= (julianday('now')-2440587.5)*86400.0))
                THEN RAISE(ABORT, 'Execution lease lost') END;
              UPDATE a2a_lite_executions SET status='done' WHERE task_id=NEW.id AND
                json_extract(NEW.status, '$.state') IN ('TASK_STATE_COMPLETED','TASK_STATE_FAILED','TASK_STATE_CANCELED','TASK_STATE_REJECTED');
              UPDATE a2a_lite_executions SET status='paused' WHERE task_id=NEW.id AND
                json_extract(NEW.status, '$.state') IN ('TASK_STATE_INPUT_REQUIRED','TASK_STATE_AUTH_REQUIRED');
            END""")
            )


class ExecutionLease:
    def __init__(self, coordinator, row, context):
        self.coordinator, self.row, self.context = coordinator, row, context
        self.backend = coordinator.backend
        self.task_id, self.fence = row["task_id"], row["fence"]
        self.checkpoint_data = json.loads(self.backend._decrypt(row["checkpoint"])) if row.get("checkpoint") else None

    async def checkpoint(self, value):
        from sqlalchemy import update

        if self.backend._closed:
            raise ExecutionLeaseLostError("Runtime is closed")
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        if len(encoded) > self.backend.config.max_checkpoint_bytes:
            raise ValueError("Checkpoint size limit exceeded")
        async with self.backend.engine.begin() as conn:
            now = await self.backend.now(conn)
            result = await conn.execute(
                update(self.backend.executions)
                .where(
                    self.backend.executions.c.task_id == self.task_id,
                    self.backend.executions.c.fence == self.fence,
                    self.backend.executions.c.status == "running",
                    self.backend.executions.c.lease_until > now,
                )
                .values(checkpoint=self.backend._encrypt(encoded))
            )
            if result.rowcount != 1:
                raise ExecutionLeaseLostError("Execution lease lost")
        self.checkpoint_data = value

    async def effect_once(self, key, operation):
        """Run an async SQL operation once, atomically with its saved result.

        operation receives this backend's AsyncConnection. Do not perform HTTP,
        email, billing or another external side effect inside this transaction.
        """
        from sqlalchemy import insert, select, update

        if self.backend._closed:
            raise ExecutionLeaseLostError("Runtime is closed")
        if not isinstance(key, str) or not key or len(key) > 255:
            raise ValueError("Effect key must contain 1–255 characters")
        table, effects = self.backend.executions, self.backend.effects
        async with self.backend.engine.begin() as conn:
            now = await self.backend.now(conn)
            # Conditional UPDATE both verifies and locks the lease in this transaction.
            locked = await conn.execute(
                update(table)
                .where(
                    table.c.task_id == self.task_id,
                    table.c.fence == self.fence,
                    table.c.status == "running",
                    table.c.lease_until > now,
                )
                .values(fence=self.fence)
            )
            if locked.rowcount != 1:
                raise ExecutionLeaseLostError("Execution lease lost")
            saved = (
                await conn.execute(
                    select(effects.c.result).where(effects.c.task_id == self.task_id, effects.c.effect_key == key)
                )
            ).scalar_one_or_none()
            if saved is not None:
                return json.loads(self.backend._decrypt(saved))
            value = await operation(conn)
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            if len(encoded) > self.backend.config.max_checkpoint_bytes:
                raise ValueError("Effect result size limit exceeded")
            await conn.execute(
                insert(effects).values(task_id=self.task_id, effect_key=key, result=self.backend._encrypt(encoded))
            )
            return value


class RecoveryCoordinator:
    def __init__(self, backend):
        self.backend = backend
        self.executor = None
        self._loop = None
        self._runners = set()
        self._heartbeats = set()
        self._leases = {}

    def _payload(self, context):
        from a2a.types import SendMessageRequest

        from .auth import AuthResult

        auth: AuthResult = context.call_context.state["auth_result"]
        request = SendMessageRequest(message=context.message)
        return self.backend._encrypt(
            json.dumps(
                {
                    "request": base64.b64encode(request.SerializeToString()).decode(),
                    "task_id": context.task_id,
                    "context_id": context.context_id,
                    "tenant": context.call_context.tenant,
                    "auth": {
                        "user_id": auth.user_id,
                        "namespace": auth.namespace,
                        "authorized_tenants": list(auth.authorized_tenants),
                        "scopes": list(auth.scopes),
                        "anonymous": auth.metadata.get("anonymous") is True,
                    },
                }
            ).encode()
        )

    async def enter(self, context, recoverable):
        from a2a.server.models import TaskModel
        from sqlalchemy import insert, select, update

        from .persistence import _sql_owner

        row = {
            "task_id": context.task_id,
            "owner": _sql_owner(context.call_context),
            "fence": str(uuid4()),
            "lease_until": 0,
            "status": "running",
            "recoverable": recoverable,
            "request_data": self._payload(context),
            "checkpoint": None,
        }
        async with self.backend.engine.begin() as conn:
            now = await self.backend.now(conn)
            row["lease_until"] = now + self.backend.config.execution_lease
            table = self.backend.executions
            existing = (
                (await conn.execute(select(table).where(table.c.task_id == context.task_id).with_for_update()))
                .mappings()
                .first()
            )
            if existing is None:
                await conn.execute(insert(table).values(**row))
            else:
                # Only an authorized new message can restart a paused task.
                # A changed fence invalidates every previous producer, including
                # one still unwinding after it emitted INPUT_REQUIRED.
                task_table = TaskModel.__table__
                paused_task = select(task_table.c.id).where(
                    task_table.c.id == context.task_id,
                    task_table.c.owner == row["owner"],
                    task_table.c.status["state"].as_string().in_(INTERRUPTED),
                )
                row["checkpoint"] = existing["checkpoint"]
                changed = await conn.execute(
                    update(table)
                    .where(
                        table.c.task_id == context.task_id,
                        table.c.owner == row["owner"],
                        table.c.fence == existing["fence"],
                        table.c.status == "paused",
                        table.c.task_id.in_(paused_task),
                    )
                    .values(**row, recovery_attempts=0)
                )
                if changed.rowcount != 1:
                    raise ExecutionLeaseLostError("Task is not available for continuation")
        lease = ExecutionLease(self, row, context.call_context)
        context.call_context.state[EXECUTION_KEY] = lease
        self.heartbeat(lease, asyncio.current_task())
        return lease

    def heartbeat(self, lease, producer):
        self._leases[lease.fence] = lease.task_id

        async def renew():
            from sqlalchemy import update

            table = self.backend.executions
            while True:
                await asyncio.sleep(self.backend.config.execution_lease / 3)
                try:
                    async with self.backend.engine.begin() as conn:
                        now = await self.backend.now(conn)
                        result = await conn.execute(
                            update(table)
                            .where(
                                table.c.task_id == lease.task_id,
                                table.c.fence == lease.fence,
                                table.c.status == "running",
                                table.c.lease_until > now,
                            )
                            .values(lease_until=now + self.backend.config.execution_lease)
                        )
                        if result.rowcount:
                            if producer and producer.done():
                                await conn.execute(
                                    update(table)
                                    .where(
                                        table.c.task_id == lease.task_id,
                                        table.c.fence == lease.fence,
                                        table.c.status == "running",
                                    )
                                    .values(lease_until=0)
                                )
                                return
                            continue
                    if producer and not producer.done():
                        producer.cancel()
                    return
                except Exception:
                    # Fail closed on storage outage; lease expiry permits reconciliation.
                    if producer and not producer.done():
                        producer.cancel()
                    return

        task = asyncio.create_task(renew())
        self._heartbeats.add(task)
        task.add_done_callback(self._heartbeats.discard)
        task.add_done_callback(lambda _: self._leases.pop(lease.fence, None))

    def start(self):
        if self.executor:
            self._loop = asyncio.create_task(self._recover_loop())

    async def claim(self):
        from sqlalchemy import select, update

        table = self.backend.executions
        async with self.backend.engine.begin() as conn:
            now = await self.backend.now(conn)
            query = select(table).where(table.c.status == "running", table.c.lease_until <= now).limit(1)
            if self.backend.engine.dialect.name == "postgresql":
                query = query.with_for_update(skip_locked=True)
            row = (await conn.execute(query)).mappings().first()
            if row is None:
                return None
            values = {
                "fence": str(uuid4()),
                "lease_until": now + self.backend.config.execution_lease,
                "recovery_attempts": row["recovery_attempts"] + 1,
            }
            changed = await conn.execute(
                update(table)
                .where(table.c.task_id == row["task_id"], table.c.fence == row["fence"], table.c.lease_until <= now)
                .values(**values)
            )
            return {**row, **values} if changed.rowcount else None

    async def _recover_loop(self):
        while True:
            try:
                state = self.executor.runtime_state
                if state.accepting and len(state.active) + len(self._runners) < state.config.max_concurrent_tasks:
                    row = await self.claim()
                    if row:
                        task = asyncio.create_task(self.resume(row))
                        self._runners.add(task)

                        def completed(task):
                            self._runners.discard(task)
                            if not task.cancelled() and task.exception() is not None:
                                from .persistence import logger

                                logger.warning("Recovered execution could not complete")

                        task.add_done_callback(completed)
            except Exception:
                # No payload, credentials, URL or raw DB error in operational logs.
                from .persistence import logger

                logger.warning("Execution recovery could not access persistence")
            await asyncio.sleep(self.backend.config.poll_interval)

    async def resume(self, row):
        from a2a.helpers import new_task_from_user_message, new_text_part
        from a2a.server.agent_execution import RequestContext
        from a2a.server.context import ServerCallContext
        from a2a.server.tasks import TaskUpdater
        from a2a.server.tasks.task_manager import TaskManager
        from a2a.types import SendMessageRequest, TaskState

        from .auth import AuthResult
        from .server import AuthenticatedUser

        payload = json.loads(self.backend._decrypt(row["request_data"]))
        auth = AuthResult.success(**payload["auth"])
        call_context = ServerCallContext(
            user=AuthenticatedUser(auth, payload["tenant"]), tenant=payload["tenant"], state={"auth_result": auth}
        )
        lease = ExecutionLease(self, row, call_context)
        call_context.state[EXECUTION_KEY] = lease
        request = SendMessageRequest.FromString(base64.b64decode(payload["request"]))
        stored = await self.backend.task_store.get(row["task_id"], call_context)
        manager = TaskManager(
            self.backend.task_store, call_context, row["task_id"], payload["context_id"], request.message
        )
        await manager.get_task()
        context = RequestContext(
            call_context,
            request=request,
            task_id=row["task_id"],
            context_id=payload["context_id"],
            task=stored.task if stored else None,
        )

        class Queue:
            async def enqueue_event(self, event):
                await manager.process(event)

        self.heartbeat(lease, asyncio.current_task())
        if row["recoverable"] and row.get("recovery_attempts", 0) <= self.backend.config.max_recovery_attempts:
            await self.executor.execute(context, Queue())
        else:
            task = stored.task if stored else new_task_from_user_message(request.message)
            task.id, task.context_id = row["task_id"], payload["context_id"]
            task.metadata[FENCE_KEY] = lease.fence
            if not stored:
                await Queue().enqueue_event(task)
            updater = TaskUpdater(Queue(), task.id, task.context_id)
            await updater.update_status(
                TaskState.TASK_STATE_FAILED,
                message=updater.new_agent_message(
                    [new_text_part("Execution interrupted; this skill does not support recovery")]
                ),
            )

    async def close(self, timeout=10.0):
        from sqlalchemy import tuple_, update

        # Revoke only this runtime's tokens. A newer replica's fence remains
        # valid. Do this before waiting for cancellation-resistant handlers.
        leases = tuple((task_id, fence) for fence, task_id in self._leases.items())

        async def revoke():
            if leases:
                table = self.backend.executions
                async with self.backend.engine.begin() as conn:
                    await conn.execute(
                        update(table)
                        .where(tuple_(table.c.task_id, table.c.fence).in_(leases), table.c.status == "running")
                        .values(fence=str(uuid4()), lease_until=0)
                    )

        revocation = asyncio.create_task(revoke())
        _, revoking = await asyncio.wait({revocation}, timeout=timeout)
        if revoking:
            revocation.cancel()
        else:
            # Surface storage failure so the caller does not claim the pool was
            # safely closed while a transaction may still own a lease.
            revocation.result()
        tasks = list(self._heartbeats | self._runners)
        if self._loop:
            tasks.append(self._loop)
        for task in tasks:
            task.cancel()
        pending = set()
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=timeout)
        for task in {*tasks, revocation}:
            task.add_done_callback(lambda finished: None if finished.cancelled() else finished.exception())
        return len(pending) + len(revoking), not revoking
