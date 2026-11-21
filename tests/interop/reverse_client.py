"""Exercise named discovery, tenant isolation and a mid-stream protocol error."""

import asyncio
import sys

from a2a_lite import AgentNetwork
from a2a_lite.errors import RemoteAgentError


async def check(url):
    network = AgentNetwork()
    tenants = ("blue", "green")
    for tenant in tenants:
        network.add(tenant, f"{url}/{tenant}")
        card = await network.discover(tenant)
        if card.url != url + "/rpc":
            raise AssertionError(f"Selected interface {card.url}")

    observed = await asyncio.gather(*(network.call(name, "tenant") for name in tenants))
    if observed != list(tenants):
        raise AssertionError(f"Expected {tenants}, received {observed}")

    chunks = []
    try:
        async for chunk in network.stream("blue", "streamError"):
            chunks.append(chunk)
    except RemoteAgentError as exc:
        if exc.code != -32602:
            raise AssertionError(f"Unexpected stream error: {exc.response}") from exc
    else:
        raise AssertionError("streamError ended without the remote error")
    if chunks != ["before-error:blue"]:
        raise AssertionError(f"Chunks delivered before error: {chunks}")
    print("A2A_LITE_STREAM_ERROR_VERIFIED")


if __name__ == "__main__":
    asyncio.run(check(sys.argv[1]))
