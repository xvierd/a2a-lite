"""
Example 18: Per-task push notifications

Demonstrates how to register a webhook for a specific task so the server
notifies you when that task completes -- without polling.

Architecture:
    1. WorkerAgent (port 8787) -- has a slow "process" skill
    2. Webhook receiver (port 9000) -- simple HTTP server that prints callbacks
    3. Client code -- delegates work, subscribes a webhook, then waits

Flow:
    Client --> WorkerAgent: POST message/send (starts "process" skill)
    Client --> WorkerAgent: POST tasks/pushNotification/set (register webhook)
    WorkerAgent finishes --> Webhook receiver: POST with task result
"""

from __future__ import annotations

import asyncio
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from a2a_lite import Agent


# ---------------------------------------------------------------------------
# 1. Worker agent with a slow skill
# ---------------------------------------------------------------------------

worker = Agent(name="WorkerAgent", description="Processes data slowly")


@worker.skill("process", description="Simulate slow processing")
async def process(data: str) -> dict:
    """Pretend to do heavy work for 3 seconds."""
    await asyncio.sleep(3)
    return {"processed": data.upper(), "length": len(data)}


# ---------------------------------------------------------------------------
# 2. Simple webhook receiver on port 9000
# ---------------------------------------------------------------------------

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        payload = json.loads(body) if body else {}
        print("\n=== Webhook received ===")
        print(json.dumps(payload, indent=2))
        print("========================\n")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):  # noqa: A002
        pass  # silence request logs


def start_webhook_server(port: int = 9000) -> HTTPServer:
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Webhook receiver listening on http://localhost:{port}/webhook")
    return server


# ---------------------------------------------------------------------------
# 3. Client code
# ---------------------------------------------------------------------------

async def main():
    # Start the webhook receiver
    webhook_server = start_webhook_server(9000)

    # In a real setup the worker would already be running on port 8787.
    # For this example you can start it in a separate terminal:
    #   python 18_per_task_push.py --serve
    # Then run the client in another terminal:
    #   python 18_per_task_push.py

    agent_url = "http://localhost:8787"

    # Delegate work and get a handle back
    client_agent = Agent(name="Client", description="Sends work")
    handle = await client_agent.delegate(
        agent_url,
        "process",
        return_handle=True,
        data="hello world",
    )
    print(f"Task submitted: {handle.task_id}")
    print(f"Immediate result: {handle.result}")

    # Subscribe to push notifications for THIS specific task
    sub = await handle.subscribe("http://localhost:9000/webhook")
    print(f"Subscribed: {sub}")

    # The webhook receiver will print the notification when the task completes.
    # In a real app you wouldn't block here -- the webhook fires asynchronously.
    print("Waiting for webhook callback (Ctrl+C to exit)...")
    try:
        await asyncio.sleep(60)
    except KeyboardInterrupt:
        pass
    finally:
        webhook_server.shutdown()


if __name__ == "__main__":
    import sys

    if "--serve" in sys.argv:
        # Run just the worker agent
        worker.run(port=8787)
    else:
        asyncio.run(main())
