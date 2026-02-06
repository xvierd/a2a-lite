"""
Tests for decorator functionality.
"""
import pytest
from a2a_lite.decorators import SkillDefinition


def test_skill_definition_creation():
    """Test SkillDefinition dataclass."""
    async def handler(x: int) -> int:
        return x

    skill = SkillDefinition(
        name="test",
        description="Test skill",
        handler=handler,
        input_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
        output_schema={"type": "integer"},
        tags=["test"],
        is_async=True,
    )

    assert skill.name == "test"
    assert skill.description == "Test skill"
    assert skill.is_async is True
    assert skill.tags == ["test"]


def test_skill_definition_to_dict():
    """Test SkillDefinition serialization."""
    async def handler() -> str:
        return "test"

    skill = SkillDefinition(
        name="test",
        description="Test skill",
        handler=handler,
        input_schema={"type": "object"},
        output_schema={"type": "string"},
        tags=["tag1", "tag2"],
    )

    data = skill.to_dict()

    assert data["name"] == "test"
    assert data["description"] == "Test skill"
    assert data["tags"] == ["tag1", "tag2"]
    assert data["input_schema"] == {"type": "object"}
    assert data["output_schema"] == {"type": "string"}
    # Handler should not be in dict (not serializable)
    assert "handler" not in data


def test_skill_definition_defaults():
    """Test SkillDefinition default values."""
    def handler() -> None:
        pass

    skill = SkillDefinition(
        name="test",
        description="Test",
        handler=handler,
        input_schema={},
        output_schema={},
    )

    assert skill.tags == []
    assert skill.is_async is False


def test_skill_definition_streaming():
    """Test SkillDefinition with streaming flag."""
    async def handler():
        yield "data"

    skill = SkillDefinition(
        name="stream",
        description="Streaming skill",
        handler=handler,
        input_schema={},
        output_schema={},
        is_streaming=True,
        is_async=True,
    )

    assert skill.is_streaming is True
    data = skill.to_dict()
    assert data["is_streaming"] is True


def test_skill_definition_task_context():
    """Test SkillDefinition with task context fields."""
    async def handler():
        return ""

    skill = SkillDefinition(
        name="tracked",
        description="Tracked skill",
        handler=handler,
        input_schema={},
        output_schema={},
        needs_task_context=True,
        task_context_param="task",
    )

    assert skill.needs_task_context is True
    assert skill.task_context_param == "task"


def test_skill_definition_auth():
    """Test SkillDefinition with auth fields."""
    async def handler():
        return ""

    skill = SkillDefinition(
        name="secure",
        description="Secure skill",
        handler=handler,
        input_schema={},
        output_schema={},
        needs_auth=True,
        auth_param="auth",
    )

    assert skill.needs_auth is True
    assert skill.auth_param == "auth"
