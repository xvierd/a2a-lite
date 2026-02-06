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

    def test_function_with_cls(self):
        """Test that 'cls' parameter is excluded."""
        class MyClass:
            @classmethod
            async def method(cls, x: int) -> int:
                return x

        input_schema, _ = extract_function_schemas(MyClass.method)
        assert "cls" not in input_schema["properties"]

    def test_function_no_return_type(self):
        """Test function without return type annotation."""
        def func(x: int):
            return x

        _, output_schema = extract_function_schemas(func)
        assert output_schema == {"type": "object"}

    def test_function_return_none(self):
        """Test function returning None."""
        def func() -> None:
            pass

        _, output_schema = extract_function_schemas(func)
        assert output_schema == {"type": "null"}

    def test_function_return_list(self):
        """Test function returning List[str]."""
        async def func() -> List[str]:
            return ["a", "b"]

        _, output_schema = extract_function_schemas(func)
        assert output_schema == {"type": "array", "items": {"type": "string"}}

    def test_empty_function(self):
        """Test function with no parameters and no return type."""
        def func():
            pass

        input_schema, output_schema = extract_function_schemas(func)
        assert input_schema["properties"] == {}
        assert input_schema["required"] == []


class TestTypeToJsonSchemaAdvanced:
    def test_union_type(self):
        """Test Union[int, str] type."""
        from typing import Union
        schema = type_to_json_schema(Union[int, str])
        assert "oneOf" in schema
        assert len(schema["oneOf"]) == 2

    def test_pydantic_model(self):
        """Test Pydantic BaseModel."""
        from pydantic import BaseModel

        class TestModel(BaseModel):
            name: str
            age: int

        schema = type_to_json_schema(TestModel)
        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "age" in schema["properties"]

    def test_optional_int(self):
        """Test Optional[int]."""
        schema = type_to_json_schema(Optional[int])
        assert schema == {"type": "integer"}

    def test_dict_str_str(self):
        """Test Dict[str, str]."""
        schema = type_to_json_schema(Dict[str, str])
        assert schema == {
            "type": "object",
            "additionalProperties": {"type": "string"},
        }

    def test_list_of_dict(self):
        """Test List[Dict[str, int]]."""
        schema = type_to_json_schema(List[Dict[str, int]])
        assert schema == {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": {"type": "integer"},
            },
        }


class TestIsOrSubclass:
    def test_exact_match(self):
        from a2a_lite.utils import _is_or_subclass
        assert _is_or_subclass(int, int) is True

    def test_subclass(self):
        from a2a_lite.utils import _is_or_subclass

        class Parent:
            pass

        class Child(Parent):
            pass

        assert _is_or_subclass(Child, Parent) is True

    def test_no_match(self):
        from a2a_lite.utils import _is_or_subclass
        assert _is_or_subclass(str, int) is False

    def test_non_type_hint(self):
        from a2a_lite.utils import _is_or_subclass
        # Generic types may raise TypeError in issubclass
        assert _is_or_subclass(List[str], int) is False
