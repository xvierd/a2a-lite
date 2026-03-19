"""
Decorator definitions and skill metadata.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillDefinition:
    """Metadata for a registered skill."""

    name: str
    description: str
    handler: Callable
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    tags: list[str] = field(default_factory=list)
    is_async: bool = False
    is_streaming: bool = False
    needs_task_context: bool = False
    needs_auth: bool = False
    needs_mcp: bool = False
    task_context_param: str | None = None
    auth_param: str | None = None
    mcp_param: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "is_streaming": self.is_streaming,
        }
