"""
Tests for the LiteAgentExecutor.
"""
import pytest
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from a2a_lite.executor import LiteAgentExecutor
from a2a_lite.decorators import SkillDefinition
from a2a_lite.middleware import MiddlewareChain, MiddlewareContext
from a2a_lite.auth import NoAuth, APIKeyAuth, AuthResult


def _make_skill(name, handler, **kwargs):
    """Helper to build a SkillDefinition from a handler function."""
    from a2a_lite.utils import extract_function_schemas
    input_schema, output_schema = extract_function_schemas(handler)
    return SkillDefinition(
        name=name,
        description=f"Skill: {name}",
        handler=handler,
        input_schema=input_schema,
        output_schema=output_schema,
        is_async=asyncio.iscoroutinefunction(handler),
        **kwargs,
    )


class TestParseMessage:
    def test_valid_json_skill_call(self):
        executor = LiteAgentExecutor(skills={})
        skill, params = executor._parse_message('{"skill": "greet", "params": {"name": "World"}}')
        assert skill == "greet"
        assert params == {"name": "World"}

    def test_json_skill_no_params(self):
        executor = LiteAgentExecutor(skills={})
        skill, params = executor._parse_message('{"skill": "hello"}')
        assert skill == "hello"
        assert params == {}

    def test_plain_text_message(self):
        executor = LiteAgentExecutor(skills={})
        skill, params = executor._parse_message("Hello there!")
        assert skill is None
        assert params == {"message": "Hello there!"}

    def test_invalid_json(self):
        executor = LiteAgentExecutor(skills={})
        skill, params = executor._parse_message("{invalid json")
        assert skill is None
        assert params == {"message": "{invalid json"}

    def test_json_without_skill_key(self):
        executor = LiteAgentExecutor(skills={})
        skill, params = executor._parse_message('{"action": "greet"}')
        assert skill is None
        assert params == {"message": '{"action": "greet"}'}


class TestExecuteSkill:
    @pytest.mark.asyncio
    async def test_no_skills_registered(self):
        executor = LiteAgentExecutor(skills={})
        result = await executor._execute_skill(None, {}, MagicMock(), {})
        assert "error" in result
        assert "No skills registered" in result["error"]

    @pytest.mark.asyncio
    async def test_auto_select_single_skill(self):
        async def greet(name: str = "World") -> str:
            return f"Hello, {name}!"

        skill = _make_skill("greet", greet)
        executor = LiteAgentExecutor(skills={"greet": skill})
        result = await executor._execute_skill(None, {"name": "Test"}, MagicMock(), {})
        assert result == "Hello, Test!"

    @pytest.mark.asyncio
    async def test_multiple_skills_no_name(self):
        async def s1() -> str:
            return "one"

        async def s2() -> str:
            return "two"

        executor = LiteAgentExecutor(skills={
            "s1": _make_skill("s1", s1),
            "s2": _make_skill("s2", s2),
        })
        result = await executor._execute_skill(None, {}, MagicMock(), {})
        assert "error" in result
        assert "available_skills" in result

    @pytest.mark.asyncio
    async def test_unknown_skill_name(self):
        async def greet() -> str:
            return "hi"

        executor = LiteAgentExecutor(skills={"greet": _make_skill("greet", greet)})
        result = await executor._execute_skill("unknown", {}, MagicMock(), {})
        assert "error" in result
        assert "Unknown skill" in result["error"]
        assert "greet" in result["available_skills"]

    @pytest.mark.asyncio
    async def test_sync_handler(self):
        def add(a: int, b: int) -> int:
            return a + b

        skill = _make_skill("add", add)
        executor = LiteAgentExecutor(skills={"add": skill})
        result = await executor._execute_skill("add", {"a": 3, "b": 4}, MagicMock(), {})
        assert result == 7

    @pytest.mark.asyncio
    async def test_async_handler(self):
        async def add(a: int, b: int) -> int:
            return a + b

        skill = _make_skill("add", add)
        executor = LiteAgentExecutor(skills={"add": skill})
        result = await executor._execute_skill("add", {"a": 5, "b": 6}, MagicMock(), {})
        assert result == 11


class TestConvertParams:
    def test_basic_params_unchanged(self):
        async def func(x: int, y: str) -> str:
            return f"{x}:{y}"

        skill = _make_skill("test", func)
        executor = LiteAgentExecutor(skills={"test": skill})
        result = executor._convert_params(skill, {"x": 42, "y": "hello"}, {})
        assert result == {"x": 42, "y": "hello"}

    def test_pydantic_model_conversion(self):
        from pydantic import BaseModel

        class User(BaseModel):
            name: str
            age: int

        async def create(user: User) -> dict:
            return {}

        skill = _make_skill("create", create)
        executor = LiteAgentExecutor(skills={"create": skill})
        result = executor._convert_params(skill, {"user": {"name": "Alice", "age": 30}}, {})
        assert isinstance(result["user"], User)
        assert result["user"].name == "Alice"
        assert result["user"].age == 30

    def test_filepart_conversion_simple_format(self):
        from a2a_lite.parts import FilePart

        async def process(file: FilePart) -> str:
            return ""

        skill = _make_skill("process", process)
        executor = LiteAgentExecutor(skills={"process": skill})
        result = executor._convert_params(
            skill,
            {"file": {"name": "test.txt", "data": "hello", "mime_type": "text/plain"}},
            {},
        )
        assert isinstance(result["file"], FilePart)
        assert result["file"].name == "test.txt"

    def test_filepart_conversion_a2a_format(self):
        import base64
        from a2a_lite.parts import FilePart

        async def process(file: FilePart) -> str:
            return ""

        skill = _make_skill("process", process)
        executor = LiteAgentExecutor(skills={"process": skill})
        result = executor._convert_params(
            skill,
            {"file": {"file": {"name": "test.txt", "bytes": base64.b64encode(b"hello").decode()}}},
            {},
        )
        assert isinstance(result["file"], FilePart)
        assert result["file"].data == b"hello"

    def test_datapart_conversion_simple(self):
        from a2a_lite.parts import DataPart

        async def analyze(data: DataPart) -> str:
            return ""

        skill = _make_skill("analyze", analyze)
        executor = LiteAgentExecutor(skills={"analyze": skill})
        result = executor._convert_params(
            skill,
            {"data": {"key": "value", "count": 42}},
            {},
        )
        assert isinstance(result["data"], DataPart)
        assert result["data"].data == {"key": "value", "count": 42}

    def test_datapart_conversion_a2a_format(self):
        from a2a_lite.parts import DataPart

        async def analyze(data: DataPart) -> str:
            return ""

        skill = _make_skill("analyze", analyze)
        executor = LiteAgentExecutor(skills={"analyze": skill})
        result = executor._convert_params(
            skill,
            {"data": {"type": "data", "data": {"key": "value"}}},
            {},
        )
        assert isinstance(result["data"], DataPart)
        assert result["data"].data == {"key": "value"}

    def test_skip_task_context_param(self):
        from a2a_lite.tasks import TaskContext

        async def process(data: str, task: TaskContext) -> str:
            return ""

        skill = _make_skill("process", process, needs_task_context=True, task_context_param="task")
        executor = LiteAgentExecutor(skills={"process": skill})
        result = executor._convert_params(
            skill,
            {"data": "test", "task": "should_be_skipped"},
            {},
        )
        assert "task" not in result
        assert result["data"] == "test"

    def test_skip_auth_result_param(self):
        async def whoami(auth: AuthResult) -> str:
            return ""

        skill = _make_skill("whoami", whoami, needs_auth=True, auth_param="auth")
        executor = LiteAgentExecutor(skills={"whoami": skill})
        result = executor._convert_params(
            skill,
            {"auth": "should_be_skipped"},
            {},
        )
        assert "auth" not in result


class TestHandleError:
    @pytest.mark.asyncio
    async def test_error_without_handler(self):
        events = []

        class MockEventQueue:
            async def enqueue_event(self, event):
                events.append(event)

        executor = LiteAgentExecutor(skills={})
        await executor._handle_error(ValueError("test error"), MockEventQueue())
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_error_with_handler(self):
        events = []

        class MockEventQueue:
            async def enqueue_event(self, event):
                events.append(event)

        async def error_handler(error):
            return {"handled": True, "error": str(error)}

        executor = LiteAgentExecutor(skills={}, error_handler=error_handler)
        await executor._handle_error(ValueError("test error"), MockEventQueue())
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_error_handler_itself_fails(self):
        events = []

        class MockEventQueue:
            async def enqueue_event(self, event):
                events.append(event)

        async def bad_handler(error):
            raise RuntimeError("handler failed too")

        executor = LiteAgentExecutor(skills={}, error_handler=bad_handler)
        await executor._handle_error(ValueError("original error"), MockEventQueue())
        assert len(events) == 1


class TestCancel:
    @pytest.mark.asyncio
    async def test_cancel(self):
        events = []

        class MockEventQueue:
            async def enqueue_event(self, event):
                events.append(event)

        executor = LiteAgentExecutor(skills={})
        await executor.cancel(MagicMock(), MockEventQueue())
        assert len(events) == 1


class TestCallHandler:
    @pytest.mark.asyncio
    async def test_async_handler(self):
        async def handler(x):
            return x * 2

        executor = LiteAgentExecutor(skills={})
        result = await executor._call_handler(handler, 5)
        assert result == 10

    @pytest.mark.asyncio
    async def test_sync_handler(self):
        def handler(x):
            return x * 3

        executor = LiteAgentExecutor(skills={})
        result = await executor._call_handler(handler, 5)
        assert result == 15
