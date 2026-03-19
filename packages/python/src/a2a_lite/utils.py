"""
Helper functions for A2A Lite.
"""

import dataclasses
import inspect
import logging
import sys
import types
import typing
from typing import Any, Union, get_args, get_origin

logger = logging.getLogger(__name__)

# Python 3.10+ introduced `X | Y` union syntax backed by types.UnionType
_UNION_TYPE = types.UnionType if sys.version_info >= (3, 10) else None


def _is_union(hint: Any) -> bool:
    """Return True if *hint* is any form of Union (typing.Union or X | Y)."""
    if get_origin(hint) is Union:
        return True
    if _UNION_TYPE is not None and isinstance(hint, _UNION_TYPE):
        return True
    return False


def _is_or_subclass(hint: Any, target_class: type) -> bool:
    """
    Check if a type hint is, or is a subclass of, the target class.

    Works with raw classes and string annotations.
    Also handles Optional[X] / X | None by extracting the inner type.
    """
    # Handle Optional[X] (Union[X, None] or X | None) by extracting the non-None type
    if _is_union(hint):
        args = get_args(hint)
        non_none_args = [a for a in args if a is not type(None)]
        if len(non_none_args) == 1:
            hint = non_none_args[0]

    try:
        if hint is target_class:
            return True
        if isinstance(hint, type) and issubclass(hint, target_class):
            return True
    except TypeError:
        pass
    return False


def type_to_json_schema(python_type: type) -> dict[str, Any]:
    """
    Convert Python type to JSON Schema.

    Handles basic types, generics (List, Dict, Optional), and Pydantic models.
    """
    # Handle None type
    if python_type is type(None):
        return {"type": "null"}

    # Basic type mapping
    type_map = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        list: {"type": "array"},
        dict: {"type": "object"},
        Any: {"type": "object"},
    }

    # Check basic types first
    if python_type in type_map:
        return type_map[python_type]

    # Handle generic types
    origin = get_origin(python_type)
    args = get_args(python_type)

    # Handle Optional[X] / X | None and other Union forms
    if _is_union(python_type):
        non_none_args = [a for a in args if a is not type(None)]
        if len(non_none_args) == 1:
            return type_to_json_schema(non_none_args[0])
        return {"oneOf": [type_to_json_schema(a) for a in args]}

    # Handle List[X]
    if origin is list and args:
        return {"type": "array", "items": type_to_json_schema(args[0])}

    # Handle Dict[K, V]
    if origin is dict and len(args) >= 2:
        return {"type": "object", "additionalProperties": type_to_json_schema(args[1])}

    # Handle Pydantic models
    if hasattr(python_type, "model_json_schema"):
        return python_type.model_json_schema()

    # Handle dataclasses
    if hasattr(python_type, "__dataclass_fields__"):
        properties = {}
        required = []
        for field_name, field_info in python_type.__dataclass_fields__.items():
            properties[field_name] = type_to_json_schema(field_info.type)
            if field_info.default is dataclasses.MISSING and field_info.default_factory is dataclasses.MISSING:
                required.append(field_name)
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    # Fallback for unknown types
    return {"type": "object"}


def extract_function_schemas(func) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Extract input and output JSON schemas from a function's type hints.

    Returns:
        Tuple of (input_schema, output_schema)
    """
    sig = inspect.signature(func)
    try:
        hints = typing.get_type_hints(func)
    except Exception as e:
        logger.debug("Failed to get type hints for %s: %s", func.__name__, e)
        hints = getattr(func, "__annotations__", {})

    # Build input schema from parameters
    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue

        param_type = hints.get(param_name, Any)
        properties[param_name] = type_to_json_schema(param_type)

        # Parameter is required if it has no default value
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    input_schema = {
        "type": "object",
        "properties": properties,
        "required": required,
    }

    # Build output schema from return type
    return_type = hints.get("return", Any)
    output_schema = type_to_json_schema(return_type)

    return input_schema, output_schema
