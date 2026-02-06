"""
Tests for the streaming module.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from a2a_lite.streaming import is_generator_function, collect_generator, stream_generator


class TestIsGeneratorFunction:
    def test_async_generator(self):
        async def gen():
            yield 1

        assert is_generator_function(gen) is True

    def test_sync_generator(self):
        def gen():
            yield 1

        assert is_generator_function(gen) is True

    def test_regular_async_function(self):
        async def func():
            return 1

        assert is_generator_function(func) is False

    def test_regular_sync_function(self):
        def func():
            return 1

        assert is_generator_function(func) is False

    def test_lambda(self):
        assert is_generator_function(lambda: 1) is False


class TestCollectGenerator:
    @pytest.mark.asyncio
    async def test_async_generator(self):
        async def gen():
            for i in range(5):
                yield i

        result = await collect_generator(gen())
        assert result == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_sync_generator(self):
        def gen():
            for i in range(3):
                yield i * 2

        result = await collect_generator(gen())
        assert result == [0, 2, 4]

    @pytest.mark.asyncio
    async def test_empty_async_generator(self):
        async def gen():
            return
            yield  # noqa: unreachable

        result = await collect_generator(gen())
        assert result == []

    @pytest.mark.asyncio
    async def test_empty_sync_generator(self):
        def gen():
            return
            yield  # noqa: unreachable

        result = await collect_generator(gen())
        assert result == []

    @pytest.mark.asyncio
    async def test_single_item_generator(self):
        async def gen():
            yield "only one"

        result = await collect_generator(gen())
        assert result == ["only one"]

    @pytest.mark.asyncio
    async def test_mixed_types_generator(self):
        async def gen():
            yield "text"
            yield 42
            yield {"key": "value"}

        result = await collect_generator(gen())
        assert result == ["text", 42, {"key": "value"}]


class TestStreamGenerator:
    @pytest.mark.asyncio
    async def test_async_generator_streaming(self):
        events = []

        class MockEventQueue:
            async def enqueue_event(self, event):
                events.append(event)

        async def gen():
            yield "hello"
            yield "world"

        await stream_generator(gen(), MockEventQueue())
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_sync_generator_streaming(self):
        events = []

        class MockEventQueue:
            async def enqueue_event(self, event):
                events.append(event)

        def gen():
            yield "one"
            yield "two"
            yield "three"

        await stream_generator(gen(), MockEventQueue())
        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_non_string_items_converted(self):
        events = []

        class MockEventQueue:
            async def enqueue_event(self, event):
                events.append(event)

        async def gen():
            yield 42
            yield 3.14

        await stream_generator(gen(), MockEventQueue())
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_empty_generator_no_events(self):
        events = []

        class MockEventQueue:
            async def enqueue_event(self, event):
                events.append(event)

        async def gen():
            return
            yield  # noqa: unreachable

        await stream_generator(gen(), MockEventQueue())
        assert len(events) == 0
