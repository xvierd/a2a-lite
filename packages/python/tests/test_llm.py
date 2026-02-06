"""
Tests for the LLM skill decorators.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from a2a_lite.llm import openai_skill, anthropic_skill, ollama_skill, _extract_user_message


class TestExtractUserMessage:
    def test_message_key(self):
        assert _extract_user_message({"message": "hello"}) == "hello"

    def test_text_key(self):
        assert _extract_user_message({"text": "hello"}) == "hello"

    def test_query_key(self):
        assert _extract_user_message({"query": "hello"}) == "hello"

    def test_prompt_key(self):
        assert _extract_user_message({"prompt": "hello"}) == "hello"

    def test_input_key(self):
        assert _extract_user_message({"input": "hello"}) == "hello"

    def test_fallback_first_string(self):
        assert _extract_user_message({"custom_name": "hello"}) == "hello"

    def test_priority_order(self):
        # message should take priority over text
        assert _extract_user_message({"text": "no", "message": "yes"}) == "yes"


class TestOpenAISkill:
    def test_non_streaming_decorator_is_callable(self):
        @openai_skill(model="gpt-4o-mini", system_prompt="You are helpful.")
        async def chat(message: str) -> str:
            ...

        # Test the wrapper function was created
        assert chat is not None
        assert callable(chat)

        import asyncio
        assert asyncio.iscoroutinefunction(chat)

    @pytest.mark.asyncio
    async def test_openai_import_error(self):
        @openai_skill(model="gpt-4o-mini")
        async def chat(message: str) -> str:
            ...

        # Should raise ImportError when openai is not installed
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(ImportError, match="openai"):
                await chat(message="hello")

    def test_streaming_decorator_creates_generator(self):
        @openai_skill(model="gpt-4o-mini", streaming=True)
        async def chat(message: str) -> str:
            ...

        import inspect
        assert inspect.isasyncgenfunction(chat)

    def test_non_streaming_decorator_is_coroutine(self):
        @openai_skill(model="gpt-4o-mini")
        async def chat(message: str) -> str:
            ...

        import asyncio
        assert asyncio.iscoroutinefunction(chat)


class TestAnthropicSkill:
    @pytest.mark.asyncio
    async def test_anthropic_import_error(self):
        @anthropic_skill(model="claude-sonnet-4-5-20250929")
        async def analyze(text: str) -> str:
            ...

        with patch.dict("sys.modules", {"anthropic": None}):
            with pytest.raises(ImportError, match="anthropic"):
                await analyze(text="hello")

    def test_streaming_decorator_creates_generator(self):
        @anthropic_skill(model="claude-sonnet-4-5-20250929", streaming=True)
        async def analyze(text: str) -> str:
            ...

        import inspect
        assert inspect.isasyncgenfunction(analyze)

    def test_non_streaming_decorator_is_coroutine(self):
        @anthropic_skill(model="claude-sonnet-4-5-20250929")
        async def analyze(text: str) -> str:
            ...

        import asyncio
        assert asyncio.iscoroutinefunction(analyze)


class TestOllamaSkill:
    def test_non_streaming_is_coroutine(self):
        @ollama_skill(model="llama3.2")
        async def local(message: str) -> str:
            ...

        import asyncio
        assert asyncio.iscoroutinefunction(local)

    def test_streaming_is_generator(self):
        @ollama_skill(model="llama3.2", streaming=True)
        async def local(message: str) -> str:
            ...

        import inspect
        assert inspect.isasyncgenfunction(local)

    @pytest.mark.asyncio
    async def test_non_streaming_calls_httpx(self):
        @ollama_skill(model="llama3.2", base_url="http://localhost:11434")
        async def local(message: str) -> str:
            ...

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "Ollama says hi"}
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await local(message="hello")
            assert result == "Ollama says hi"


class TestDecoratorPreservesMetadata:
    def test_openai_preserves_name(self):
        @openai_skill(model="gpt-4o-mini")
        async def my_chat(message: str) -> str:
            ...

        assert my_chat.__name__ == "my_chat"

    def test_anthropic_preserves_name(self):
        @anthropic_skill(model="claude-sonnet-4-5-20250929")
        async def my_analyze(text: str) -> str:
            ...

        assert my_analyze.__name__ == "my_analyze"

    def test_ollama_preserves_name(self):
        @ollama_skill(model="llama3.2")
        async def my_local(message: str) -> str:
            ...

        assert my_local.__name__ == "my_local"
