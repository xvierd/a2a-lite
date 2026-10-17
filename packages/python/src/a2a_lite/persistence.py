"""Optional SQL state, event stream and transactional callback outbox.

Schema changes are explicit: await config.migrate() before starting a runtime.
State persistence does not restart arbitrary Python coroutine executions.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from uuid import uuid4

logger = logging.getLogger(__name__)
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PersistenceConfig:
    url: str = field(repr=False)
    encryption_key: str | bytes = field(repr=False)
    schema: str | None = None
    encryption_key_id: str = "default"
    previous_encryption_keys: dict[str, str | bytes] = field(default_factory=dict, repr=False)
    poll_interval: float = 0.1
    callback_attempts: int = 5
    callback_max_age: float = 86400.0
    max_push_configs: int = 16
    callback_retry_delay: float = 1.0
    callback_lease: float = 30.0
    dispatch_callbacks: bool = True
    execution_lease: float = 30.0
    max_checkpoint_bytes: int = 65536
    max_recovery_attempts: int = 3

    def __post_init__(self):
        import math

        if not self.url.startswith(("postgresql+asyncpg://", "sqlite+aiosqlite://")):
            raise ValueError("Use postgresql+asyncpg or sqlite+aiosqlite")
        if self.schema and (
            not self.url.startswith("postgresql") or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", self.schema)
        ):
            raise ValueError("schema must be a simple PostgreSQL identifier")
        for name in ("poll_interval", "callback_retry_delay", "callback_lease", "execution_lease", "callback_max_age"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")
        if not isinstance(self.max_push_configs, int) or self.max_push_configs < 1:
            raise ValueError("max_push_configs must be positive")
        if not isinstance(self.max_checkpoint_bytes, int) or self.max_checkpoint_bytes < 1:
            raise ValueError("max_checkpoint_bytes must be positive")
        if not isinstance(self.max_recovery_attempts, int) or self.max_recovery_attempts < 1:
            raise ValueError("max_recovery_attempts must be positive")
        if self.callback_lease < 12:
            raise ValueError("callback_lease must exceed the 10 second delivery deadline")
        if not isinstance(self.callback_attempts, int) or self.callback_attempts < 1:
            raise ValueError("callback_attempts must be a positive integer")
        from cryptography.fernet import Fernet

        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", self.encryption_key_id):
            raise ValueError("encryption_key_id must be a simple nonsecret identifier")
        Fernet(self.encryption_key)
        for key_id, key in self.previous_encryption_keys.items():
            if key_id == self.encryption_key_id or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", key_id):
                raise ValueError("Invalid or duplicate previous encryption key ID")
            Fernet(key)

    def build(self):
        return DatabaseBackend(self)

    async def migrate(self):
        """Create/validate schema v1. Run once during deployment, before replicas."""
        backend = self.build()
        try:
            await backend.migrate()
        finally:
            await backend.close()


def _sql_owner(context):
    # Fixed-width DB key avoids the SDK VARCHAR(255) limit without truncation.
    # The request handler has already authenticated and tenant-scoped user_name.
    return "sha256:" + hashlib.sha256(context.user.user_name.encode()).hexdigest()


class DatabaseBackend:
    def __init__(self, config):
        try:
            from a2a.server.cluster.database_event_stream import DatabaseTaskEventStream
            from a2a.server.cluster.database_task_store import VersionedDatabaseTaskStore
            from a2a.server.tasks.database_push_notification_config_store import DatabasePushNotificationConfigStore
            from a2a.server.tasks.push_notification_sender import PushNotificationSender
            from cryptography.fernet import Fernet
            from sqlalchemy import BigInteger, Column, Float, Integer, LargeBinary, MetaData, String, Table
            from sqlalchemy.ext.asyncio import create_async_engine
        except ImportError as error:
            raise ImportError("Install a2a-lite[sqlite] or a2a-lite[postgresql]") from error
        self.config = config
        self.fernet = Fernet(config.encryption_key)
        self.keyring = {key_id: Fernet(key) for key_id, key in config.previous_encryption_keys.items()}
        self.keyring[config.encryption_key_id] = self.fernet
        connect_args = {"server_settings": {"search_path": config.schema}} if config.schema else {}
        self.engine = create_async_engine(
            config.url, connect_args=connect_args, pool_pre_ping=True, hide_parameters=True
        )
        from .recovery import CANCEL_FENCE, CANCEL_KEY, EXECUTION_KEY, FENCE_KEY

        class FencedTaskStore(VersionedDatabaseTaskStore):
            async def save(self, task, *, context, **kwargs):
                from a2a.types import TaskState

                lease = context.state.get(EXECUTION_KEY)
                if context.state.get(CANCEL_KEY) is True and task.status.state == TaskState.TASK_STATE_CANCELED:
                    # Set only by the authenticated CancelTask boundary. Producer
                    # CANCELED events must still pass the transactional fence.
                    task.metadata[FENCE_KEY] = CANCEL_FENCE
                elif lease is not None:
                    from sqlalchemy import select

                    from .recovery import ExecutionLeaseLostError

                    if lease.backend._closed:
                        raise ExecutionLeaseLostError("Runtime is closed")
                    table = lease.backend.executions
                    async with lease.backend.engine.connect() as conn:
                        now = await lease.backend.now(conn)
                        valid = (
                            await conn.execute(
                                select(table.c.fence).where(
                                    table.c.task_id == lease.task_id,
                                    table.c.fence == lease.fence,
                                    table.c.lease_until > now,
                                )
                            )
                        ).scalar_one_or_none()
                    if valid is None:
                        raise ExecutionLeaseLostError("Execution lease lost")
                    task.metadata[FENCE_KEY] = lease.fence
                return await super().save(task, context=context, **kwargs)

        self.task_store = FencedTaskStore(self.engine, create_table=False, owner_resolver=_sql_owner)
        self.event_stream = DatabaseTaskEventStream(
            self.engine, create_table=False, poll_interval_s=config.poll_interval
        )
        self.push_store = DatabasePushNotificationConfigStore(
            self.engine,
            create_table=False,
            encryption_key=config.encryption_key,
            owner_resolver=_sql_owner,
            model_to_core_conversion=self._decode_config,
            core_to_model_conversion=self._encode_config,
        )

        class TransactionalSender(PushNotificationSender):
            async def send_notification(self, task_id, event):
                # The DB trigger already queued callbacks atomically with this event.
                return None

        self.push_sender = TransactionalSender()
        self.metadata = MetaData()
        self.schema_table = Table(
            "a2a_lite_schema",
            self.metadata,
            Column("id", Integer, primary_key=True),
            Column("version", Integer, nullable=False),
        )
        self.outbox = Table(
            "a2a_lite_outbox",
            self.metadata,
            Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
            Column("task_id", String(36), nullable=False),
            Column("task_version", BigInteger, nullable=False),
            Column("config_id", String(255), nullable=False),
            Column("config_data", LargeBinary, nullable=False),
            Column("event_data", LargeBinary, nullable=False),
            Column("status", String(16), nullable=False, server_default="pending"),
            Column("attempts", Integer, nullable=False, server_default="0"),
            Column("due", Float, nullable=False, server_default="0"),
            Column("lease_until", Float, nullable=False, server_default="0"),
            Column("lease_token", String(36)),
            Column("completed_at", Float),
            Column("created_at", Float, nullable=False, server_default="0"),
        )
        from .recovery import RecoveryCoordinator, add_tables

        add_tables(self)
        self.recovery = RecoveryCoordinator(self)
        self._worker = None
        self._client = None
        self._closed = False
        self.last_dispatch_error = False

    def _encrypt(self, payload):
        return b"a2a-lite:v1:" + self.config.encryption_key_id.encode() + b":" + self.fernet.encrypt(payload)

    def _decrypt(self, envelope):
        prefix, version, key_id, ciphertext = envelope.split(b":", 3)
        if prefix != b"a2a-lite" or version != b"v1":
            raise ValueError("Unsupported encrypted configuration envelope")
        return self.keyring[key_id.decode()].decrypt(ciphertext)

    def _encode_config(self, task_id, config, owner, _fernet):
        from google.protobuf.json_format import MessageToJson

        return self.push_store.config_model(
            task_id=task_id,
            config_id=config.id,
            owner=owner,
            config_data=self._encrypt(MessageToJson(config).encode()),
            protocol_version="1.0",
        )

    def _decode_config(self, row):
        from a2a.types import TaskPushNotificationConfig
        from google.protobuf.json_format import Parse

        return Parse(self._decrypt(row.config_data).decode(), TaskPushNotificationConfig())

    async def migrate(self):
        from a2a.server.models import Base
        from sqlalchemy import insert, select, text

        async with self.engine.begin() as conn:
            if self.config.schema:
                await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{self.config.schema}"'))
            await conn.run_sync(self.metadata.create_all, tables=[self.schema_table])
            version = (
                await conn.execute(select(self.schema_table.c.version).where(self.schema_table.c.id == 1))
            ).scalar_one_or_none()
            if version is not None and version != SCHEMA_VERSION:
                raise RuntimeError("Unsupported persistence schema version")
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(self.metadata.create_all)
            if self.engine.dialect.name == "postgresql":
                await conn.execute(
                    text("""CREATE OR REPLACE FUNCTION a2a_lite_queue_callback() RETURNS trigger AS $$
                BEGIN
                  INSERT INTO a2a_lite_outbox (task_id, task_version, config_id, config_data, event_data, created_at)
                  SELECT NEW.task_id, NEW.task_version, p.config_id, p.config_data, NEW.event_data, EXTRACT(EPOCH FROM clock_timestamp())
                  FROM push_notification_configs p WHERE p.task_id=NEW.task_id AND p.owner=NEW.owner;
                  RETURN NEW;
                END; $$ LANGUAGE plpgsql""")
                )
                await conn.execute(text("DROP TRIGGER IF EXISTS a2a_lite_callback_event ON task_events"))
                await conn.execute(
                    text("""CREATE TRIGGER a2a_lite_callback_event AFTER INSERT ON task_events
                    FOR EACH ROW EXECUTE FUNCTION a2a_lite_queue_callback()""")
                )
            else:
                await conn.execute(
                    text("""CREATE TRIGGER IF NOT EXISTS a2a_lite_callback_event AFTER INSERT ON task_events
                BEGIN
                  INSERT INTO a2a_lite_outbox (task_id, task_version, config_id, config_data, event_data, created_at)
                  SELECT NEW.task_id, NEW.task_version, p.config_id, p.config_data, NEW.event_data, (julianday('now')-2440587.5)*86400.0
                  FROM push_notification_configs p WHERE p.task_id=NEW.task_id AND p.owner=NEW.owner;
                END""")
                )
            if self.engine.dialect.name == "postgresql":
                await conn.execute(
                    text("""CREATE OR REPLACE FUNCTION a2a_lite_cancel_callback() RETURNS trigger AS $$
                BEGIN
                  UPDATE a2a_lite_outbox SET status='canceled', lease_token=NULL, lease_until=0
                  WHERE task_id=OLD.task_id AND config_id=OLD.config_id AND status IN ('pending','sending','dead');
                  RETURN OLD;
                END; $$ LANGUAGE plpgsql""")
                )
                await conn.execute(text("DROP TRIGGER IF EXISTS a2a_lite_callback_delete ON push_notification_configs"))
                await conn.execute(
                    text("""CREATE TRIGGER a2a_lite_callback_delete AFTER DELETE ON push_notification_configs
                    FOR EACH ROW EXECUTE FUNCTION a2a_lite_cancel_callback()""")
                )
            else:
                await conn.execute(
                    text("""CREATE TRIGGER IF NOT EXISTS a2a_lite_callback_delete AFTER DELETE ON push_notification_configs
                BEGIN UPDATE a2a_lite_outbox SET status='canceled', lease_token=NULL, lease_until=0
                  WHERE task_id=OLD.task_id AND config_id=OLD.config_id AND status IN ('pending','sending','dead'); END""")
                )
            if self.engine.dialect.name == "postgresql":
                await conn.execute(
                    text(f"""CREATE OR REPLACE FUNCTION a2a_lite_push_limit() RETURNS trigger AS $$
                BEGIN
                  PERFORM id FROM tasks WHERE id=NEW.task_id FOR UPDATE;
                  IF (SELECT count(*) FROM push_notification_configs WHERE task_id=NEW.task_id AND owner=NEW.owner) >= {self.config.max_push_configs}
                  THEN RAISE EXCEPTION 'Push configuration limit exceeded'; END IF;
                  RETURN NEW;
                END; $$ LANGUAGE plpgsql""")
                )
                await conn.execute(text("DROP TRIGGER IF EXISTS a2a_lite_push_limit ON push_notification_configs"))
                await conn.execute(
                    text("""CREATE TRIGGER a2a_lite_push_limit BEFORE INSERT ON push_notification_configs
                    FOR EACH ROW EXECUTE FUNCTION a2a_lite_push_limit()""")
                )
            else:
                await conn.execute(
                    text(f"""CREATE TRIGGER IF NOT EXISTS a2a_lite_push_limit BEFORE INSERT ON push_notification_configs
                WHEN (SELECT count(*) FROM push_notification_configs WHERE task_id=NEW.task_id AND owner=NEW.owner) >= {self.config.max_push_configs}
                BEGIN SELECT RAISE(ABORT, 'Push configuration limit exceeded'); END""")
                )
            from .recovery import migrate_fences

            await migrate_fences(conn, self)
            if version is None:
                await conn.execute(insert(self.schema_table).values(id=1, version=SCHEMA_VERSION))

    async def check(self):
        from sqlalchemy import select, text

        try:
            async with self.engine.connect() as conn:
                version = (
                    await conn.execute(select(self.schema_table.c.version).where(self.schema_table.c.id == 1))
                ).scalar_one()
                if version != SCHEMA_VERSION:
                    raise RuntimeError("Unsupported persistence schema version")
                # Validate dependencies too: a version row alone is insufficient.
                from a2a.server.models import TaskEventModel, TaskModel, TaskVersionModel

                for table in (
                    TaskModel.__table__,
                    TaskEventModel.__table__,
                    TaskVersionModel.__table__,
                    self.push_store.config_model.__table__,
                    self.outbox,
                    self.executions,
                    self.effects,
                ):
                    await conn.execute(select(table).limit(0))
                required = {"a2a_lite_callback_event", "a2a_lite_callback_delete", "a2a_lite_push_limit"}
                if self.engine.dialect.name == "postgresql":
                    required.add("a2a_lite_execution_write")
                    names = (
                        (
                            await conn.execute(
                                text(
                                    "SELECT tgname FROM pg_trigger WHERE tgrelid IN ('task_events'::regclass, 'tasks'::regclass, 'push_notification_configs'::regclass) AND NOT tgisinternal"
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                else:
                    required.update(("a2a_lite_execution_insert", "a2a_lite_execution_update"))
                    names = (
                        (await conn.execute(text("SELECT name FROM sqlite_master WHERE type='trigger'")))
                        .scalars()
                        .all()
                    )
                if not required.issubset(names):
                    raise RuntimeError("Required persistence triggers are missing")
        except Exception as error:
            raise RuntimeError("Persistence is unavailable or schema is not migrated") from error

    async def start(self):
        await self.check()
        await self.task_store.initialize()
        await self.event_stream.initialize()
        await self.push_store.initialize()
        self.recovery.start()
        if self.config.dispatch_callbacks:
            from .push_notifications import create_push_http_client

            self._client = create_push_http_client()
            self._worker = asyncio.create_task(self._dispatch_loop())

    async def now(self, conn):
        """Database clock is the sole authority for distributed leases/deadlines."""
        from sqlalchemy import text

        statement = (
            "SELECT EXTRACT(EPOCH FROM clock_timestamp())"
            if self.engine.dialect.name == "postgresql"
            else "SELECT (julianday('now')-2440587.5)*86400.0"
        )
        return float((await conn.execute(text(statement))).scalar_one())

    async def _claim(self):
        from sqlalchemy import and_, select, update

        async with self.engine.begin() as conn:
            now = await self.now(conn)
            eligible = and_(
                self.outbox.c.status.in_(("pending", "sending")),
                self.outbox.c.due <= now,
                self.outbox.c.lease_until <= now,
            )
            await conn.execute(
                update(self.outbox)
                .where(
                    eligible,
                    (self.outbox.c.attempts >= self.config.callback_attempts)
                    | (self.outbox.c.created_at < now - self.config.callback_max_age),
                )
                .values(status="dead", completed_at=now, lease_token=None)
            )
            query = select(self.outbox).where(eligible).order_by(self.outbox.c.id).limit(1)
            if self.engine.dialect.name == "postgresql":
                query = query.with_for_update(skip_locked=True)
            row = (await conn.execute(query)).mappings().first()
            if not row:
                return None
            token = str(uuid4())
            result = await conn.execute(
                update(self.outbox)
                .where(self.outbox.c.id == row["id"], eligible)
                .values(
                    status="sending",
                    lease_token=token,
                    lease_until=now + self.config.callback_lease,
                    attempts=self.outbox.c.attempts + 1,
                )
            )
            return {**row, "lease_token": token, "attempts": row["attempts"] + 1} if result.rowcount else None

    async def _deliver(self, row):
        from types import SimpleNamespace

        from a2a.types import StreamResponse
        from google.protobuf.json_format import MessageToDict

        from .push_notifications import validate_callback_url

        config = self._decode_config(SimpleNamespace(config_data=row["config_data"]))
        if not await validate_callback_url(config.url):
            return False
        payload = StreamResponse.FromString(row["event_data"])
        identity = f"{row['task_id']}:{row['task_version']}:{row['config_id']}"
        headers = {
            "Content-Type": "application/a2a+json",
            "X-A2A-Delivery-Id": hashlib.sha256(identity.encode()).hexdigest(),
        }
        if config.token:
            headers["X-A2A-Notification-Token"] = config.token
        if config.authentication.scheme and config.authentication.credentials:
            headers["Authorization"] = f"{config.authentication.scheme} {config.authentication.credentials}"
        return await self._client.post_callback(config.url, json=MessageToDict(payload), headers=headers)

    async def dispatch_once(self):
        """Process at most one persisted delivery; exposed for deterministic workers/tests."""
        import random

        from sqlalchemy import update

        row = await self._claim()
        if row is None:
            return False
        try:
            success = await asyncio.wait_for(self._deliver(row), timeout=10)
        except Exception:
            success = False
        terminal = success or row["attempts"] >= self.config.callback_attempts
        status = "delivered" if success else "dead" if terminal else "pending"
        async with self.engine.begin() as conn:
            now = await self.now(conn)
            await conn.execute(
                update(self.outbox)
                .where(
                    self.outbox.c.id == row["id"],
                    self.outbox.c.lease_token == row["lease_token"],
                )
                .values(
                    status=status,
                    lease_until=0,
                    lease_token=None,
                    due=now
                    + self.config.callback_retry_delay * 2 ** min(row["attempts"] - 1, 10) * random.uniform(0.5, 1.5),
                    completed_at=now if terminal else None,
                )
            )
        return True

    async def _dispatch_loop(self):
        while True:
            try:
                processed = await self.dispatch_once()
                self.last_dispatch_error = False
            except Exception:
                # DB/URL exceptions can contain credentials; never include them.
                logger.warning("Durable callback worker could not process a delivery")
                self.last_dispatch_error = True
                processed = False
            if not processed:
                await asyncio.sleep(self.config.poll_interval)

    async def callback_stats(self):
        from sqlalchemy import func, select

        async with self.engine.connect() as conn:
            rows = await conn.execute(select(self.outbox.c.status, func.count()).group_by(self.outbox.c.status))
            return dict(rows.all())

    async def retry_dead(self, delivery_id):
        """Open a fresh retry/age budget, retaining the original delivery identity."""
        from sqlalchemy import update

        async with self.engine.begin() as conn:
            now = await self.now(conn)
            result = await conn.execute(
                update(self.outbox)
                .where(self.outbox.c.id == delivery_id, self.outbox.c.status == "dead")
                .values(
                    status="pending",
                    attempts=0,
                    due=0,
                    lease_until=0,
                    lease_token=None,
                    completed_at=None,
                    created_at=now,
                )
            )
            return bool(result.rowcount)

    async def rotate_encryption(self):
        """Re-encrypt stored configs/outbox snapshots after adding a new current key.

        Keep previous keys configured on every replica until this completes and
        old-key replicas are stopped. Updates compare ciphertext to avoid races.
        """
        from sqlalchemy import select, tuple_, update

        configs = self.push_store.config_model.__table__
        for table, keys, columns in (
            (configs, ("task_id", "config_id"), ("config_data",)),
            (self.outbox, ("id",), ("config_data",)),
            (self.executions, ("task_id",), ("request_data", "checkpoint")),
            (self.effects, ("task_id", "effect_key"), ("result",)),
        ):
            last = None
            while True:
                query = select(table).order_by(*(table.c[key] for key in keys)).limit(500)
                if last:
                    query = query.where(tuple_(*(table.c[key] for key in keys)) > tuple_(*last))
                async with self.engine.begin() as conn:
                    rows = (await conn.execute(query)).mappings().all()
                    for row in rows:
                        for column in columns:
                            if row[column] is not None:
                                await conn.execute(
                                    update(table)
                                    .where(
                                        *(table.c[key] == row[key] for key in keys),
                                        table.c[column] == row[column],
                                    )
                                    .values({column: self._encrypt(self._decrypt(row[column]))})
                                )
                if not rows:
                    break
                last = tuple(rows[-1][key] for key in keys)

    async def cleanup(self, older_than):
        """Delete terminal tasks and their event/config/effect history in a batch.

        older_than is a UTC datetime. Pending, sending or dead-letter callbacks
        retain their task; inspect/replay/delete those explicitly first.
        """
        from a2a.server.models import TaskEventModel, TaskModel, TaskVersionModel
        from sqlalchemy import delete, select

        from .recovery import TERMINAL

        task_table = TaskModel.__table__
        async with self.engine.begin() as conn:
            protected = select(self.outbox.c.task_id).where(self.outbox.c.status.in_(("pending", "sending", "dead")))
            rows = (
                await conn.execute(
                    select(task_table.c.id)
                    .where(
                        task_table.c.last_updated < older_than.replace(tzinfo=None),
                        task_table.c.status["state"].as_string().in_(TERMINAL),
                        ~task_table.c.id.in_(protected),
                    )
                    .order_by(task_table.c.last_updated, task_table.c.id)
                    .limit(500)
                )
            ).all()
            ids = [row.id for row in rows]
            if not ids:
                return 0
            for table in (
                self.outbox,
                self.push_store.config_model.__table__,
                self.effects,
                self.executions,
                TaskEventModel.__table__,
                TaskVersionModel.__table__,
            ):
                await conn.execute(delete(table).where(table.c.task_id.in_(ids)))
            await conn.execute(delete(task_table).where(task_table.c.id.in_(ids)))
            return len(ids)

    async def close(self, timeout=10.0):
        if self._closed:
            return 0
        self._closed = True
        uncooperative, revoked = await self.recovery.close(timeout)
        if self._worker:
            self._worker.cancel()
            _, pending = await asyncio.wait({self._worker}, timeout=timeout)
            uncooperative += len(pending)
        if self._client:
            await self._client.aclose()
        if revoked:
            await self.engine.dispose()
        return uncooperative
