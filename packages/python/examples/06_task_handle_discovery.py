"""
Example: TaskHandle and Agent Card Discovery

Demonstrates:
1. Using discover=True to fetch a remote agent's card before delegating
2. Using return_handle=True to get a TaskHandle with task_id metadata
3. Using get_remote_task() to check the status of a completed task

Run:
    # Terminal 1: Start the DataAgent
    # Terminal 2: Start the OrchestratorAgent
    python examples/06_task_handle_discovery.py data
    python examples/06_task_handle_discovery.py orchestrator
"""

import sys

from a2a_lite import Agent, AgentNetwork, get_remote_task


def create_data_agent():
    """A data agent that provides lookup results."""
    agent = Agent(
        name="DataAgent",
        description="Provides data lookups for various topics",
    )

    @agent.skill("lookup", description="Look up data for a given topic")
    async def lookup(topic: str) -> dict:
        # Simulated data store
        data = {
            "weather": {"temp": "72F", "condition": "Sunny"},
            "stocks": {"AAPL": 185.50, "GOOG": 141.20},
            "news": {"headline": "AI agents are everywhere"},
        }
        return data.get(topic, {"error": f"No data for '{topic}'"})

    return agent


def create_orchestrator_agent():
    """An orchestrator that discovers the DataAgent before delegating."""
    network = AgentNetwork()
    network.add("data", "http://localhost:8787")

    agent = Agent(
        name="OrchestratorAgent",
        description="Orchestrates calls to the DataAgent with discovery and task handles",
        network=network,
    )

    @agent.skill("research", description="Research a topic using the DataAgent")
    async def research(topic: str) -> dict:
        # Step 1: Delegate with discover=True to validate the skill exists on the
        # remote agent before calling it, and return_handle=True to get a TaskHandle
        # with the task_id for later reference.
        handle = await agent.delegate(
            "data",
            "lookup",
            discover=True,
            return_handle=True,
            topic=topic,
        )

        # Step 2: The TaskHandle wraps the result and includes the task_id
        print(f"Task ID: {handle.task_id}")
        print(f"Agent URL: {handle.agent_url}")
        print(f"Result:  {handle.result}")

        # Step 3: Use the handle's convenience methods to check task status
        # (This queries the A2A protocol's tasks/get endpoint.)
        try:
            status = await handle.get_status()
            print(f"Task status (via handle): {status}")
        except Exception as e:
            # The remote agent may not support tasks/get; that's fine
            print(f"Could not fetch task status via handle: {e}")

        # Step 4: Or use the network's convenience methods
        try:
            status = await network.get_task("data", handle.task_id)
            print(f"Task status (via network): {status}")
        except Exception as e:
            print(f"Could not fetch task status via network: {e}")

        # Step 5: Cancel if needed (commented out to avoid canceling a completed task)
        # await handle.cancel()
        # await network.cancel_task("data", handle.task_id)

        return {
            "topic": topic,
            "task_id": handle.task_id,
            "data": handle.result,
        }

    return agent


if __name__ == "__main__":
    role = sys.argv[1] if len(sys.argv) > 1 else "orchestrator"

    if role == "data":
        create_data_agent().run(port=8787)
    else:
        create_orchestrator_agent().run(port=8788)
