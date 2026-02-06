"""
Tests for middleware functionality.
"""
import pytest
from a2a_lite.middleware import (
    MiddlewareContext,
    MiddlewareChain,
    logging_middleware,
    timing_middleware,
    retry_middleware,
    rate_limit_middleware,
    RateLimitExceeded,
)


def test_middleware_context_creation():
    """Test MiddlewareContext dataclass."""
    ctx = MiddlewareContext(
        skill="test_skill",
        params={"a": 1, "b": 2},
        message='{"skill": "test"}',
    )
    assert ctx.skill == "test_skill"
    assert ctx.params == {"a": 1, "b": 2}
    assert ctx.metadata == {}


def test_middleware_chain():
    """Test middleware chain execution."""
    chain = MiddlewareChain()
    order = []

    async def middleware1(ctx, next):
        order.append("m1_before")
        result = await next()
        order.append("m1_after")
        return result

    async def middleware2(ctx, next):
        order.append("m2_before")
        result = await next()
        order.append("m2_after")
        return result

    chain.add(middleware1)
    chain.add(middleware2)

    async def final_handler(ctx):
        order.append("handler")
        return "result"

    import asyncio
    ctx = MiddlewareContext(skill="test")
    result = asyncio.run(chain.execute(ctx, final_handler))

    assert result == "result"
    assert order == ["m1_before", "m2_before", "handler", "m2_after", "m1_after"]


@pytest.mark.asyncio
async def test_timing_middleware():
    """Test timing middleware adds execution time."""
    import asyncio

    middleware = timing_middleware()
    ctx = MiddlewareContext(skill="test")

    async def slow_handler(ctx):
        await asyncio.sleep(0.1)
        return "done"

    chain = MiddlewareChain()
    chain.add(middleware)

    await chain.execute(ctx, slow_handler)

    assert "execution_time_ms" in ctx.metadata
    assert ctx.metadata["execution_time_ms"] >= 100


@pytest.mark.asyncio
async def test_retry_middleware():
    """Test retry middleware retries on failure."""
    attempts = []

    async def flaky_handler(ctx):
        attempts.append(1)
        if len(attempts) < 3:
            raise ValueError("Not yet!")
        return "success"

    middleware = retry_middleware(max_retries=3, delay=0.01)
    chain = MiddlewareChain()
    chain.add(middleware)

    ctx = MiddlewareContext(skill="test")
    result = await chain.execute(ctx, flaky_handler)

    assert result == "success"
    assert len(attempts) == 3


@pytest.mark.asyncio
async def test_rate_limit_middleware():
    """Test rate limiting."""
    middleware = rate_limit_middleware(requests_per_minute=2)

    async def handler(ctx):
        return "ok"

    chain = MiddlewareChain()
    chain.add(middleware)

    # First two requests should work
    ctx1 = MiddlewareContext(skill="test")
    await chain.execute(ctx1, handler)

    ctx2 = MiddlewareContext(skill="test")
    await chain.execute(ctx2, handler)

    # Third should fail
    ctx3 = MiddlewareContext(skill="test")
    with pytest.raises(RateLimitExceeded):
        await chain.execute(ctx3, handler)
