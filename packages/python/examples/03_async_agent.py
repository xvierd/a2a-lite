"""
Agent demonstrating async operations.

Run with: python examples/03_async_agent.py
Test with: a2a-lite test http://localhost:8787 fetch_data -p url=https://httpbin.org/json
"""
import asyncio
from typing import Dict, Any, List
from a2a_lite import Agent

agent = Agent(
    name="AsyncDemo",
    description="Demonstrates async operations in A2A Lite",
    version="1.0.0",
)


@agent.skill("delay", description="Wait for specified seconds and return")
async def delay(seconds: float = 1.0) -> dict:
    """Waits for the specified duration."""
    await asyncio.sleep(seconds)
    return {
        "waited": seconds,
        "message": f"Waited for {seconds} seconds",
    }


@agent.skill("fetch_data", description="Fetch data from a URL")
async def fetch_data(url: str) -> Dict[str, Any]:
    """Fetches JSON data from the given URL."""
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()

        return {
            "status": response.status_code,
            "data": response.json(),
        }


@agent.skill("parallel_fetch", description="Fetch multiple URLs in parallel")
async def parallel_fetch(urls: List[str]) -> Dict[str, Any]:
    """Fetches multiple URLs concurrently."""
    import httpx

    async def fetch_one(client: httpx.AsyncClient, url: str) -> dict:
        try:
            response = await client.get(url, timeout=10.0)
            return {"url": url, "status": response.status_code, "success": True}
        except Exception as e:
            return {"url": url, "error": str(e), "success": False}

    async with httpx.AsyncClient() as client:
        tasks = [fetch_one(client, url) for url in urls]
        results = await asyncio.gather(*tasks)

    return {
        "total": len(urls),
        "successful": sum(1 for r in results if r["success"]),
        "results": results,
    }


@agent.on_startup
async def startup():
    print("Agent is starting up...")


@agent.on_shutdown
async def shutdown():
    print("Agent is shutting down...")


if __name__ == "__main__":
    agent.run(port=8787)
