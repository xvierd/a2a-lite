"""
Example: Using middleware for logging, timing, auth, etc.

Middleware lets you add cross-cutting concerns without touching skill code.

Run: python examples/07_middleware.py
"""
import time
from a2a_lite import Agent, logging_middleware, timing_middleware


agent = Agent(
    name="MiddlewareDemo",
    description="Shows how to use middleware",
)


# Option 1: Use built-in middleware
agent.add_middleware(timing_middleware())


# Option 2: Create custom middleware with decorator
@agent.middleware
async def my_logger(ctx, next):
    """Log every request."""
    print(f"📥 Request: skill={ctx.skill}, params={ctx.params}")
    start = time.time()

    result = await next()

    elapsed = (time.time() - start) * 1000
    print(f"📤 Response: {elapsed:.1f}ms")
    return result


@agent.middleware
async def add_metadata(ctx, next):
    """Add metadata to context (available to other middleware/handlers)."""
    ctx.metadata["request_id"] = f"req-{int(time.time())}"
    return await next()


# Skills - they don't need to know about middleware!
@agent.skill("slow_operation")
async def slow_operation(seconds: float = 1.0) -> dict:
    """Simulate a slow operation."""
    import asyncio
    await asyncio.sleep(seconds)
    return {"waited": seconds, "message": "Done!"}


@agent.skill("fast_operation")
async def fast_operation(x: int) -> dict:
    """Quick calculation."""
    return {"result": x * 2}


if __name__ == "__main__":
    agent.run(port=8787)
