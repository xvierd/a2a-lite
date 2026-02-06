"""
Tests for utility functions.
"""
import pytest
from typing import List, Dict, Optional, Any
from a2a_lite.utils import type_to_json_schema, extract_function_schemas


class TestTypeToJsonSchema:
    """Tests for type_to_json_schema function."""

    def test_basic_types(self):
        """Test basic Python types."""
        assert type_to_json_schema(str) == {"type": "string"}
        assert type_to_json_schema(int) == {"type": "integer"}
        assert type_to_json_schema(float) == {"type": "number"}
        assert type_to_json_schema(bool) == {"type": "boolean"}
        assert type_to_json_schema(list) == {"type": "array"}
        assert type_to_json_schema(dict) == {"type": "object"}

    def test_none_type(self):
        """Test None type."""
        assert type_to_json_schema(type(None)) == {"type": "null"}

    def test_any_type(self):
        """Test Any type."""
        assert type_to_json_schema(Any) == {"type": "object"}

    def test_list_generic(self):
        """Test List[X] generic."""
        schema = type_to_json_schema(List[str])
        assert schema == {"type": "array", "items": {"type": "string"}}

    def test_list_of_int(self):
        """Test List[int]."""
        schema = type_to_json_schema(List[int])
        assert schema == {"type": "array", "items": {"type": "integer"}}

    def test_dict_generic(self):
        """Test Dict[K, V] generic."""
        schema = type_to_json_schema(Dict[str, int])
        assert schema == {
            "type": "object",
            "additionalProperties": {"type": "integer"}
        }

    def test_optional_type(self):
        """Test Optional[X] type."""
        schema = type_to_json_schema(Optional[str])
        assert schema == {"type": "string"}

    def test_nested_list(self):
        """Test nested List[List[X]]."""
        schema = type_to_json_schema(List[List[int]])
        assert schema == {
            "type": "array",
            "items": {
                "type": "array",
                "items": {"type": "integer"}
            }
        }

    def test_unknown_type_fallback(self):
        """Test fallback for unknown types."""
        class CustomClass:
            pass

        schema = type_to_json_schema(CustomClass)
        assert schema == {"type": "object"}


class TestExtractFunctionSchemas:
    """Tests for extract_function_schemas function."""

    def test_simple_function(self):
        """Test schema extraction from simple function."""
        async def add(a: int, b: int) -> int:
            return a + b

        input_schema, output_schema = extract_function_schemas(add)

        assert input_schema["type"] == "object"
        assert input_schema["properties"]["a"] == {"type": "integer"}
        assert input_schema["properties"]["b"] == {"type": "integer"}
        assert set(input_schema["required"]) == {"a", "b"}
        assert output_schema == {"type": "integer"}

    def test_function_with_defaults(self):
        """Test schema extraction with default parameters."""
        async def greet(name: str = "World") -> str:
            return f"Hello, {name}"

        input_schema, output_schema = extract_function_schemas(greet)

        assert "name" in input_schema["properties"]
        assert "name" not in input_schema["required"]

    def test_function_with_complex_types(self):
        """Test schema extraction with complex types."""
        async def process(items: List[str], options: Dict[str, Any]) -> List[Dict[str, Any]]:
            return []

        input_schema, output_schema = extract_function_schemas(process)

        assert input_schema["properties"]["items"] == {
            "type": "array",
            "items": {"type": "string"}
        }
        assert input_schema["properties"]["options"] == {
            "type": "object",
            "additionalProperties": {"type": "object"}
        }

    def test_function_no_annotations(self):
        """Test schema extraction with no annotations."""
        def no_hints(x, y):
            return x + y

        input_schema, output_schema = extract_function_schemas(no_hints)

        # Should default to object type
        assert input_schema["properties"]["x"] == {"type": "object"}
        assert input_schema["properties"]["y"] == {"type": "object"}

    def test_function_with_self(self):
        """Test that 'self' parameter is excluded."""
        class MyClass:
            async def method(self, x: int) -> int:
                return x

        input_schema, _ = extract_function_schemas(MyClass.method)

        assert "self" not in input_schema["properties"]
        assert "x" in input_schema["properties"]
