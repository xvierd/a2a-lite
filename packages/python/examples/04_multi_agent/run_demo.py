"""
Demo script showing multi-agent communication.

This script:
1. Tests the Finance agent directly
2. Tests the Reporter agent (which calls Finance agent)

Prerequisites:
  - Start finance_agent.py on port 8787
  - Start reporter_agent.py on port 8788
"""
import asyncio
import json
import httpx
from uuid import uuid4


SAMPLE_EXPENSES = [
    {"description": "Uber ride to airport", "amount": 45.00},
    {"description": "Coffee at Starbucks", "amount": 5.50},
    {"description": "Netflix subscription", "amount": 15.99},
    {"description": "Grocery shopping at Whole Foods", "amount": 127.43},
    {"description": "Gas station fill-up", "amount": 55.00},
    {"description": "Amazon purchase", "amount": 89.99},
    {"description": "Restaurant dinner", "amount": 78.50},
    {"description": "Electric bill payment", "amount": 95.00},
]


async def call_agent(url: str, skill: str, params: dict) -> dict:
    """Call an A2A agent skill."""
    message = json.dumps({"skill": skill, "params": params})

    request_body = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": uuid4().hex,
        "params": {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": message}],
                "messageId": uuid4().hex,
            }
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=request_body, timeout=30.0)
        response.raise_for_status()
        return response.json()


async def main():
    print("=" * 60)
    print("A2A Lite Multi-Agent Demo")
    print("=" * 60)

    # Test 1: Call Finance agent directly
    print("\n1. Testing Finance Agent (port 8787)")
    print("-" * 40)

    try:
        result = await call_agent(
            "http://localhost:8787",
            "categorize",
            {"description": "Uber ride", "amount": 25.00}
        )
        print("Single categorization result:")
        print(json.dumps(result, indent=2))
    except httpx.ConnectError:
        print("ERROR: Finance agent not running on port 8787")
        print("Start it with: python examples/04_multi_agent/finance_agent.py")
        return

    # Test 2: Bulk categorization
    print("\n2. Bulk Categorization")
    print("-" * 40)

    result = await call_agent(
        "http://localhost:8787",
        "analyze_spending",
        {"expenses": SAMPLE_EXPENSES}
    )
    print("Spending analysis:")
    print(json.dumps(result, indent=2))

    # Test 3: Call Reporter agent (which calls Finance agent)
    print("\n3. Testing Reporter Agent (port 8788)")
    print("-" * 40)

    try:
        result = await call_agent(
            "http://localhost:8788",
            "generate_report",
            {"expenses": SAMPLE_EXPENSES}
        )
        print("Report from Reporter agent:")
        print(json.dumps(result, indent=2))
    except httpx.ConnectError:
        print("ERROR: Reporter agent not running on port 8788")
        print("Start it with: python examples/04_multi_agent/reporter_agent.py")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
