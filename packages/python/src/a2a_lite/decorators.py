"""
Decorator definitions and skill metadata.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class SkillDefinition:
    """Metadata for a registered skill."""
    name: str
    description: str
    handler: Callable
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    tags: List[str] = field(default_factory=list)
    is_async: bool = False
    is_streaming: bool = False
    needs_task_context: bool = False
    needs_auth: bool = False
    task_context_param: Optional[str] = None
    auth_param: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "is_streaming": self.is_streaming,
        }
