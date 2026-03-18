"""
Persistence Lite — pluggable TaskStore + PushNotifier example.

Shows how to:
  1. Swap the protocol-level TaskStore (e.g. use Redis/Postgres in production
     by replacing InMemoryTaskStore with your own implementation).
  2. Use LogPushNotifier during development (zero config).
  3. Switch to WebhookPushNotifier for production by setting WEBHOOK_URL (and
     optionally WEBHOOK_SECRET) environment variables.
  4. Wire both into an Agent with only a few extra lines.

Run (dev mode, no env vars needed):
    python agent.py

Run (production mode with webhook):
    WEBHOOK_URL=https://hooks.example.com/a2a python agent.py

Optionally sign payloads:
    WEBHOOK_URL=https://hooks.example.com/a2a WEBHOOK_SECRET=mysecret python agent.py
"""

from __future__ import annotations

import asyncio
import os

from a2a.server.tasks import InMemoryTaskStore

from a2a_lite import Agent
from a2a_lite.push_notifications import LogPushNotifier, WebhookPushNotifier

# ---------------------------------------------------------------------------
# Push notifier — dev vs production
# ---------------------------------------------------------------------------

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")  # optional

if WEBHOOK_URL:
    # Production: POST completed-task events to a real webhook endpoint.
    # Set WEBHOOK_SECRET to have each request signed with HMAC-SHA256.
    push_notifier = WebhookPushNotifier(
        url=WEBHOOK_URL,
        secret=WEBHOOK_SECRET,  # None → no signature header
        timeout=5.0,
        max_retries=2,
    )
else:
    # Development: just log events — no external service needed.
    push_notifier = LogPushNotifier()

# ---------------------------------------------------------------------------
# Protocol-level TaskStore
# ---------------------------------------------------------------------------
# In a real application you would swap InMemoryTaskStore() for a persistent
# implementation (e.g. a Redis-backed store).  Passing it explicitly here
# makes the seam visible and easy to test.

protocol_store = InMemoryTaskStore()

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

agent = Agent(
    name="PersistenceLiteAgent",
    description=(
        "Demonstrates pluggable TaskStore and PushNotifier. "
        "Uses LogPushNotifier in dev and WebhookPushNotifier when "
        "WEBHOOK_URL is set."
    ),
    version="1.0.0",
    # Hand the explicit store to the protocol layer.
    protocol_task_store=protocol_store,
    # Every completed skill invocation triggers the notifier.
    push_notifier=push_notifier,
)


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


@agent.skill("echo", description="Return the input message unchanged.")
async def echo(message: str) -> dict:
    """Echo the caller's message back."""
    return {"echo": message}


@agent.skill(
    "slow_sum",
    description=(
        "Add two integers with a simulated delay. "
        "Demonstrates a long-running skill alongside push notifications."
    ),
)
async def slow_sum(a: int, b: int, delay: float = 1.0) -> dict:
    """Add a + b after sleeping for *delay* seconds (default 1 s)."""
    await asyncio.sleep(delay)
    return {
        "a": a,
        "b": b,
        "sum": a + b,
        "delay_seconds": delay,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    notifier_type = "WebhookPushNotifier" if WEBHOOK_URL else "LogPushNotifier"
    print(f"Push notifier : {notifier_type}")
    if WEBHOOK_URL:
        print(f"Webhook URL   : {WEBHOOK_URL}")
        print(f"Signed        : {'yes' if WEBHOOK_SECRET else 'no'}")
    print(f"TaskStore     : {type(protocol_store).__name__}")
    print()

    agent.run(port=8793)
