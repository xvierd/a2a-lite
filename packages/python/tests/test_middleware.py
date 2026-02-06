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


@pytest.mark.asyncio
async def test_empty_middleware_chain():
    """Test that an empty chain just calls the final handler."""
    chain = MiddlewareChain()

    async def handler(ctx):
        return "direct"

    ctx = MiddlewareContext(skill="test")
    result = await chain.execute(ctx, handler)
    assert result == "direct"


@pytest.mark.asyncio
async def test_middleware_modifying_result():
    """Test that middleware can modify the result."""
    chain = MiddlewareChain()

    async def double_middleware(ctx, next):
        result = await next()
        return result * 2

    chain.add(double_middleware)

    async def handler(ctx):
        return 21

    ctx = MiddlewareContext(skill="test")
    result = await chain.execute(ctx, handler)
    assert result == 42


@pytest.mark.asyncio
async def test_middleware_short_circuit():
    """Test that middleware can short-circuit and skip the handler."""
    chain = MiddlewareChain()

    async def guard_middleware(ctx, next):
        if ctx.skill == "blocked":
            return {"error": "blocked"}
        return await next()

    chain.add(guard_middleware)

    async def handler(ctx):
        return "should not reach"

    ctx = MiddlewareContext(skill="blocked")
    result = await chain.execute(ctx, handler)
    assert result == {"error": "blocked"}


@pytest.mark.asyncio
async def test_middleware_metadata_sharing():
    """Test that middleware can share data through metadata."""
    chain = MiddlewareChain()

    async def middleware1(ctx, next):
        ctx.metadata["added_by_m1"] = True
        return await next()

    async def middleware2(ctx, next):
        ctx.metadata["added_by_m2"] = True
        ctx.metadata["saw_m1"] = ctx.metadata.get("added_by_m1", False)
        return await next()

    chain.add(middleware1)
    chain.add(middleware2)

    async def handler(ctx):
        return ctx.metadata

    ctx = MiddlewareContext(skill="test")
    result = await chain.execute(ctx, handler)
    assert result["added_by_m1"] is True
    assert result["added_by_m2"] is True
    assert result["saw_m1"] is True


@pytest.mark.asyncio
async def test_logging_middleware():
    """Test that logging middleware doesn't break the chain."""
    chain = MiddlewareChain()
    chain.add(logging_middleware())

    async def handler(ctx):
        return "ok"

    ctx = MiddlewareContext(skill="test_skill", params={"a": 1})
    result = await chain.execute(ctx, handler)
    assert result == "ok"


@pytest.mark.asyncio
async def test_logging_middleware_with_error():
    """Test that logging middleware re-raises errors."""
    chain = MiddlewareChain()
    chain.add(logging_middleware())

    async def handler(ctx):
        raise ValueError("test error")

    ctx = MiddlewareContext(skill="test_skill")
    with pytest.raises(ValueError, match="test error"):
        await chain.execute(ctx, handler)


@pytest.mark.asyncio
async def test_retry_middleware_all_retries_fail():
    """Test retry middleware when all retries fail."""
    attempts = []

    async def always_fails(ctx):
        attempts.append(1)
        raise ValueError("always fails")

    middleware = retry_middleware(max_retries=3, delay=0.01)
    chain = MiddlewareChain()
    chain.add(middleware)

    ctx = MiddlewareContext(skill="test")
    with pytest.raises(ValueError, match="always fails"):
        await chain.execute(ctx, always_fails)

    assert len(attempts) == 3


@pytest.mark.asyncio
async def test_middleware_context_defaults():
    """Test MiddlewareContext default values."""
    ctx = MiddlewareContext()
    assert ctx.skill is None
    assert ctx.params == {}
    assert ctx.message == ""
    assert ctx.metadata == {}


@pytest.mark.asyncio
async def test_multiple_middlewares_combined():
    """Test combining timing and logging middleware."""
    import asyncio

    chain = MiddlewareChain()
    chain.add(logging_middleware())
    chain.add(timing_middleware())

    async def handler(ctx):
        await asyncio.sleep(0.05)
        return "done"

    ctx = MiddlewareContext(skill="test")
    result = await chain.execute(ctx, handler)
    assert result == "done"
    assert "execution_time_ms" in ctx.metadata
    assert ctx.metadata["execution_time_ms"] >= 50
