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
