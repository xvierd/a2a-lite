"""
Middleware support for A2A Lite agents.

Middleware allows you to add cross-cutting concerns like logging,
authentication, rate limiting, etc.

Example:
    @agent.middleware
    async def log_requests(ctx, next):
        print(f"Request: {ctx.skill}")
        result = await next()
        print(f"Result: {result}")
        return result
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import asyncio


@dataclass
class MiddlewareContext:
    """
    Context passed to middleware functions.

    Attributes:
        skill: The skill being called (if determined)
        params: The parameters for the skill
        message: The raw message text
        metadata: Arbitrary metadata dict for middleware to share data
    """

    skill: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class MiddlewareChain:
    """
    Manages the middleware execution chain.

    Middleware functions are called in order, each receiving the context
    and a `next` function to call the next middleware (or the final handler).
    """

    def __init__(self):
        self._middlewares: List[Callable] = []

    def add(self, middleware: Callable) -> None:
        """Add a middleware function to the chain."""
        self._middlewares.append(middleware)

    async def execute(
        self,
        context: MiddlewareContext,
        final_handler: Callable,
    ) -> Any:
        """
        Execute the middleware chain.

        Args:
            context: The middleware context
            final_handler: The final handler to call after all middleware

        Returns:
            The result from the handler (possibly modified by middleware)
        """

        # Build the chain from the end
        async def call_final():
            return await final_handler(context)

        # Wrap each middleware around the next
        next_fn = call_final
        for middleware in reversed(self._middlewares):
            next_fn = self._wrap_middleware(middleware, context, next_fn)

        return await next_fn()

    def _wrap_middleware(
        self,
        middleware: Callable,
        context: MiddlewareContext,
        next_fn: Callable,
    ) -> Callable:
        """Wrap a middleware function."""

        async def wrapped():
            if asyncio.iscoroutinefunction(middleware):
                return await middleware(context, next_fn)
            else:
                return middleware(context, next_fn)

        return wrapped


# Built-in middleware helpers


def logging_middleware(logger=None):
    """
    Create a logging middleware.

    Example:
        agent.add_middleware(logging_middleware())
    """
    import logging

    log = logger or logging.getLogger("a2a_lite")

    async def middleware(ctx: MiddlewareContext, next):
        log.info(f"Calling skill: {ctx.skill} with params: {ctx.params}")
        try:
            result = await next()
            log.info(f"Skill {ctx.skill} returned successfully")
            return result
        except Exception as e:
            log.error(f"Skill {ctx.skill} failed: {e}")
            raise

    return middleware


def timing_middleware():
    """
    Create a timing middleware that adds execution time to metadata.

    Example:
        agent.add_middleware(timing_middleware())
    """
    import time

    async def middleware(ctx: MiddlewareContext, next):
        start = time.perf_counter()
        result = await next()
        elapsed = time.perf_counter() - start
        ctx.metadata["execution_time_ms"] = round(elapsed * 1000, 2)
        return result

    return middleware


def retry_middleware(max_retries: int = 3, delay: float = 1.0):
    """
    Create a retry middleware for failed skill calls.

    Example:
        agent.add_middleware(retry_middleware(max_retries=3))
    """

    async def middleware(ctx: MiddlewareContext, next):
        last_error = None
        for attempt in range(max_retries):
            try:
                return await next()
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay * (attempt + 1))
        raise last_error

    return middleware


def rate_limit_middleware(requests_per_minute: int = 60):
    """
    Create a simple in-process rate limiting middleware.

    Note: This rate limiter is per-process. Under multi-worker uvicorn
    (e.g., ``--workers 4``), each worker tracks limits independently.
    For shared rate limiting across workers, use an external store
    (Redis, etc.) and a custom middleware.

    Example:
        agent.add_middleware(rate_limit_middleware(requests_per_minute=100))
    """
    import time
    from collections import deque

    request_times = deque()

    async def middleware(ctx: MiddlewareContext, next):
        now = time.time()
        minute_ago = now - 60

        # Remove old requests
        while request_times and request_times[0] < minute_ago:
            request_times.popleft()

        if len(request_times) >= requests_per_minute:
            raise RateLimitExceeded(
                f"Rate limit exceeded: {requests_per_minute} requests per minute"
            )

        request_times.append(now)
        return await next()

    return middleware


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""

    pass
