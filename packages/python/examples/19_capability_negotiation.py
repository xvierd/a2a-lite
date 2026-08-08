"""
Example 19: Agent Capability Negotiation via Discovery + TaskHandle

Two-agent negotiation pattern where an orchestrator:
1. Discovers each candidate agent's published capabilities (agent card)
2. Validates the required skill exists before committing
3. Delegates with return_handle=True to track the task
4. Monitors task lifecycle via TaskHandle

Pattern — Capability-Based Negotiation:

    OrchestratorAgent
         │
         ├── discover("http://localhost:8787") → reads /.well-known/agent.json
         ├── discover("http://localhost:8788") → reads /.well-known/agent.json
         │
         │   selects the agent that has the "analyze" skill
         │
         └── delegate(selected, "analyze", discover=True, return_handle=True)
                  │
                  ├── handle.task_id  → unique task ID
                  ├── handle.result   → immediate result
                  └── handle.get_status() → polls tasks/get on remote

Run:
    # Terminal 1 — specialist A (has "analyze" skill):
    python examples/19_capability_negotiation.py specialist_a

    # Terminal 2 — specialist B (has "summarize" skill, not "analyze"):
    python examples/19_capability_negotiation.py specialist_b

    # Terminal 3 — orchestrator (discovers + selects + delegates):
    python examples/19_capability_negotiation.py orchestrator
"""
from __future__ import annotations

import asyncio
import sys

from a2a_lite import Agent, AgentNetwork, discover


# ---------------------------------------------------------------------------
# Specialist A — port 8787 — has the "analyze" skill
# ---------------------------------------------------------------------------

def create_specialist_a() -> Agent:
    agent = Agent(
        name="AnalystAgent",
        description="Deep text analysis specialist",
        version="1.0.0",
    )

    @agent.skill("analyze", description="Deep analysis of a text document")
    async def analyze(text: str) -> dict:
        words = text.split()
        sentences = [s.strip() for s in text.split(".") if s.strip()]
        avg_word_len = sum(len(w) for w in words) / max(len(words), 1)
        return {
            "agent": "AnalystAgent",
            "word_count": len(words),
            "sentence_count": len(sentences),
            "avg_word_length": round(avg_word_len, 2),
            "complexity": "high" if avg_word_len > 5 else "low",
        }

    return agent


# ---------------------------------------------------------------------------
# Specialist B — port 8788 — has the "summarize" skill (NOT "analyze")
# ---------------------------------------------------------------------------

def create_specialist_b() -> Agent:
    agent = Agent(
        name="SummarizerAgent",
        description="Text summarization specialist",
        version="1.0.0",
    )

    @agent.skill("summarize", description="Summarize a long document into bullet points")
    async def summarize(text: str, max_points: int = 3) -> dict:
        sentences = [s.strip() for s in text.split(".") if s.strip()]
        bullets = sentences[:max_points]
        return {
            "agent": "SummarizerAgent",
            "bullets": bullets,
            "total_sentences": len(sentences),
        }

    return agent


# ---------------------------------------------------------------------------
# Orchestrator — discovers, negotiates, delegates
# ---------------------------------------------------------------------------

def create_orchestrator() -> Agent:
    network = AgentNetwork()
    network.add("specialist_a", "http://localhost:8787")
    network.add("specialist_b", "http://localhost:8788")

    orchestrator = Agent(
        name="OrchestratorAgent",
        description="Negotiates with specialist agents based on their published capabilities",
        network=network,
    )

    @orchestrator.skill(
        "find_and_analyze",
        description="Discover available agents, pick the one with 'analyze' skill, then delegate",
    )
    async def find_and_analyze(text: str) -> dict:
        candidates = {
            "specialist_a": "http://localhost:8787",
            "specialist_b": "http://localhost:8788",
        }

        # --- Phase 1: Discovery / Negotiation --------------------------------
        # Read each agent's published card and find who has the "analyze" skill.
        selected_name = None
        selected_card = None

        for name, url in candidates.items():
            try:
                card = await discover(url)
                skill_ids = [s.id for s in card.skills]
                print(f"  [{name}] skills: {skill_ids}")

                if "analyze" in skill_ids:
                    selected_name = name
                    selected_card = card
                    print(f"  → Selected {name} ({card.name}) — has 'analyze'")
                    break
            except Exception as e:
                print(f"  [{name}] discovery failed: {e}")

        if not selected_name:
            return {"error": "No agent with 'analyze' skill found during negotiation"}

        # --- Phase 2: Delegation with TaskHandle -----------------------------
        # delegate with discover=True re-validates the skill exists on the
        # remote agent just before calling. return_handle=True gives us the
        # task ID for lifecycle tracking.
        handle = await orchestrator.delegate(
            selected_name,
            "analyze",
            discover=True,       # re-validate before committing
            return_handle=True,  # get TaskHandle back
            text=text,
        )

        print(f"\n  Task submitted — id: {handle.task_id}")
        print(f"  Remote agent URL: {handle.agent_url}")
        print(f"  Immediate result: {handle.result}")

        # --- Phase 3: Task Lifecycle -----------------------------------------
        # Poll the remote task store to confirm status.
        try:
            status = await handle.get_status()
            print(f"  Task status (handle.get_status): {status}")
        except Exception as e:
            print(f"  Note: tasks/get not available on remote: {e}")

        # Could cancel if the result doesn't meet criteria:
        # if handle.result.get("complexity") == "high":
        #     await handle.cancel()
        #     return {"error": "Text too complex, task cancelled"}

        return {
            "negotiated_agent": selected_card.name if selected_card else selected_name,
            "task_id": handle.task_id,
            "analysis": handle.result,
        }

    return orchestrator


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    role = sys.argv[1] if len(sys.argv) > 1 else "orchestrator"

    if role == "specialist_a":
        print("Starting AnalystAgent on port 8787 ...")
        create_specialist_a().run(port=8787)
    elif role == "specialist_b":
        print("Starting SummarizerAgent on port 8788 ...")
        create_specialist_b().run(port=8788)
    else:
        print("Starting OrchestratorAgent on port 8789 ...")
        create_orchestrator().run(port=8789)
