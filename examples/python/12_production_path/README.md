# Python learning-to-production path

No LLM account, external callback or database server is needed.

```bash
# From the repository root:
pip install -e 'packages/python[sqlite]'
python examples/python/12_production_path/main.py
python examples/python/12_production_path/main.py --durable-directory /tmp/a2a-learning-state
```

The first run shows an immediate Message, a Task whose injected ID can be queried remotely, ordered streaming, header authentication and runtime statistics. The SQLite run adds schema migration, a checkpointed skill, restart and API key rotation while preserving task ownership. Its local demonstration key is persisted with mode 0600; production keys belong in your secret manager.

A recoverable handler starts from its beginning and reads `task.checkpoint_data`. The checkpoint example has no external effects. `task.effect_once(key, operation)` is for a transaction against the same database; external email/payment/HTTP calls need receiver idempotency. See the [runtime and persistence guide](../../../packages/python/docs/production.md) and the real PostgreSQL recovery tests before using multiple replicas.
