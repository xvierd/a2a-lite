"""
Example 20: Streaming Negotiation Between Two Agents

Two-agent negotiation where one agent streams proposal chunks and the other
consumes them in real-time to make an incremental decision.

Pattern — Streaming Negotiation:

    ReviewAgent ──(delegate stream=True)──► ProposalAgent
                                                 │ yield chunk 1  (price: $100)
                 ◄── chunk 1 ────────────────────┘
                                                 │ yield chunk 2  (price: $90)
                 ◄── chunk 2 ────────────────────┘
                                                 │ yield chunk 3  (price: $80)
                 ◄── chunk 3 ────────────────────┘

    ReviewAgent accumulates each chunk and accepts/rejects based on price
    threshold — decision made before the stream ends.

Use case: budget negotiation, real-time bid evaluation, incremental scoring.

Run:
    # Terminal 1 — ProposalAgent (streams descending price offers):
    python examples/20_streaming_negotiation.py proposal

    # Terminal 2 — ReviewAgent (consumes stream, accepts first offer ≤ budget):
    python examples/20_streaming_negotiation.py review

    # Terminal 3 — Trigger a negotiation:
    curl -s -X POST http://localhost:8788 \\
      -H "Content-Type: application/json" \\
      -d '{
        "jsonrpc":"2.0","method":"message/send","id":"1",
        "params":{"message":{"role":"user","parts":[{"type":"text",
          "text":"{\\"skill\\":\\"negotiate\\",\\"params\\":{\\"item\\":\\"GPU server\\",\\"budget\\":85}}"}],
          "messageId":"m1"}}
      }' | python3 -m json.tool
"""
from __future__ import annotations

import asyncio
import sys

from a2a_lite import Agent, AgentNetwork


# ---------------------------------------------------------------------------
# ProposalAgent — streams descending price offers
# ---------------------------------------------------------------------------

def create_proposal_agent() -> Agent:
    agent = Agent(
        name="ProposalAgent",
        description="Streams a series of price proposals for an item",
    )

    @agent.skill(
        "make_offers",
        streaming=True,
        description="Stream descending price offers until budget is met or offers exhausted",
    )
    async def make_offers(item: str, starting_price: float = 200.0, steps: int = 5):
        """
        Yields one JSON-serialisable string per offer round.
        Each chunk represents a negotiation step.
        """
        price = starting_price
        discount_per_step = starting_price * 0.10  # 10 % per step

        for step in range(1, steps + 1):
            offer = {
                "step": step,
                "item": item,
                "price": round(price, 2),
                "currency": "USD",
                "final_offer": step == steps,
            }
            # Yield as a formatted string so the ReviewAgent can parse it
            import json
            yield json.dumps(offer) + "\n"

            price -= discount_per_step
            await asyncio.sleep(0.3)  # simulate deliberation time

    return agent


# ---------------------------------------------------------------------------
# ReviewAgent — consumes the stream and decides
# ---------------------------------------------------------------------------

def create_review_agent() -> Agent:
    network = AgentNetwork()
    network.add("proposal", "http://localhost:8787")

    agent = Agent(
        name="ReviewAgent",
        description="Negotiates by consuming a streaming offer from ProposalAgent",
        network=network,
    )

    @agent.skill(
        "negotiate",
        description="Open a streaming negotiation with ProposalAgent and accept the first offer within budget",
    )
    async def negotiate(item: str, budget: float) -> dict:
        import json

        accepted_offer = None
        all_offers = []

        print(f"\n[ReviewAgent] Starting negotiation for '{item}' — budget: ${budget}")

        # Consume the ProposalAgent's stream in real-time.
        # Each chunk is one JSON line with price + metadata.
        async for chunk in await agent.delegate(
            "proposal",
            "make_offers",
            stream=True,   # ← real-time SSE consumption
            item=item,
            starting_price=budget * 2,  # seller starts at 2x buyer budget
            steps=6,
        ):
            chunk = chunk.strip()
            if not chunk:
                continue

            try:
                offer = json.loads(chunk)
            except json.JSONDecodeError:
                continue

            all_offers.append(offer)
            print(f"  [stream] step {offer['step']} — ${offer['price']}", end="")

            if offer["price"] <= budget and accepted_offer is None:
                accepted_offer = offer
                print(" ✓ ACCEPTED", end="")

            print()  # newline

        # Decision summary
        if accepted_offer:
            result = {
                "outcome": "deal",
                "item": item,
                "agreed_price": accepted_offer["price"],
                "accepted_at_step": accepted_offer["step"],
                "total_steps_streamed": len(all_offers),
                "savings_vs_opening": round(all_offers[0]["price"] - accepted_offer["price"], 2),
            }
        else:
            result = {
                "outcome": "no_deal",
                "item": item,
                "budget": budget,
                "lowest_offer": all_offers[-1]["price"] if all_offers else None,
                "total_steps_streamed": len(all_offers),
            }

        print(f"\n[ReviewAgent] Negotiation complete: {result['outcome'].upper()}")
        return result

    return agent


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    role = sys.argv[1] if len(sys.argv) > 1 else "proposal"

    if role == "proposal":
        print("Starting ProposalAgent on port 8787 ...")
        create_proposal_agent().run(port=8787)
    else:
        print("Starting ReviewAgent on port 8788 ...")
        create_review_agent().run(port=8788)
