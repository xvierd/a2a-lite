"""
Helper functions for A2A Lite.
"""

import typing
from typing import Any, Dict, Type, get_origin, get_args, Union
import inspect


def _is_or_subclass(hint: Any, target_class: Type) -> bool:
    """
    Check if a type hint is, or is a subclass of, the target class.

    Works with raw classes and string annotations.
    Also handles Optional[X] (Union[X, None]) by extracting the inner type.
    """
    # Handle Optional[X] (Union[X, None]) by extracting the non-None type
    origin = get_origin(hint)
    if origin is Union:
        args = get_args(hint)
        non_none_args = [a for a in args if a is not type(None)]
        if len(non_none_args) == 1:
            # This is Optional[X], check against the inner type
            hint = non_none_args[0]

    try:
        if hint is target_class:
            return True
        if isinstance(hint, type) and issubclass(hint, target_class):
            return True
    except TypeError:
        pass
    return False


def type_to_json_schema(python_type: Type) -> Dict[str, Any]:
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

    # Handle Optional (Union[X, None])
    if origin is Union:
        non_none_args = [a for a in args if a is not type(None)]
        if len(non_none_args) == 1:
            # This is Optional[X]
            return type_to_json_schema(non_none_args[0])
        # Union of multiple types
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
            if (
                field_info.default is inspect.Parameter.empty
                and field_info.default_factory is inspect.Parameter.empty
            ):
                required.append(field_name)
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    # Fallback for unknown types
    return {"type": "object"}


def extract_function_schemas(func) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Extract input and output JSON schemas from a function's type hints.

    Returns:
        Tuple of (input_schema, output_schema)
    """
    sig = inspect.signature(func)
    try:
        hints = typing.get_type_hints(func)
    except Exception:
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
