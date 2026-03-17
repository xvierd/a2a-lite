"""
Calculator Skill Implementations

This module provides arithmetic operations as A2A skills.
Each function represents one skill with proper validation and error handling.
"""

from typing import Any, Dict


class SkillError(Exception):
    """Exception for skill execution errors."""
    pass


def add(a: float, b: float) -> Dict[str, Any]:
    """
    Add two numbers.
    
    Args:
        a: First number
        b: Second number
        
    Returns:
        Dictionary with result
    """
    _validate_numbers(a, b)
    return {"result": a + b}


def subtract(a: float, b: float) -> Dict[str, Any]:
    """
    Subtract b from a.
    
    Args:
        a: First number
        b: Second number
        
    Returns:
        Dictionary with result
    """
    _validate_numbers(a, b)
    return {"result": a - b}


def multiply(a: float, b: float) -> Dict[str, Any]:
    """
    Multiply two numbers.
    
    Args:
        a: First number
        b: Second number
        
    Returns:
        Dictionary with result
    """
    _validate_numbers(a, b)
    return {"result": a * b}


def divide(a: float, b: float) -> Dict[str, Any]:
    """
    Divide a by b.
    
    Args:
        a: Dividend
        b: Divisor
        
    Returns:
        Dictionary with result and remainder
        
    Raises:
        SkillError: If dividing by zero
    """
    _validate_numbers(a, b)
    
    if b == 0:
        raise SkillError("Division by zero is not allowed")
    
    return {
        "result": a / b,
        "remainder": a % b
    }


def power(base: float, exponent: float) -> Dict[str, Any]:
    """
    Raise base to the power of exponent.
    
    Args:
        base: Base number
        exponent: Exponent
        
    Returns:
        Dictionary with result
    """
    _validate_numbers(base, exponent)
    return {"result": base ** exponent}


def _validate_numbers(*numbers: float) -> None:
    """
    Validate that all arguments are numbers.
    
    Args:
        *numbers: Numbers to validate
        
    Raises:
        SkillError: If any argument is not a number
    """
    for n in numbers:
        if not isinstance(n, (int, float)):
            raise SkillError(f"Expected number, got {type(n).__name__}")


# Skill registry mapping names to functions
SKILL_REGISTRY = {
    "add": add,
    "subtract": subtract,
    "multiply": multiply,
    "divide": divide,
    "power": power,
}


def execute_skill(skill_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a calculator skill.
    
    Args:
        skill_name: Name of the skill to execute
        params: Parameters for the skill
        
    Returns:
        Skill execution result
        
    Raises:
        SkillError: If skill not found or execution fails
    """
    if skill_name not in SKILL_REGISTRY:
        available = ", ".join(SKILL_REGISTRY.keys())
        raise SkillError(f"Unknown skill: {skill_name}. Available: {available}")
    
    skill_func = SKILL_REGISTRY[skill_name]
    
    try:
        return skill_func(**params)
    except TypeError as e:
        raise SkillError(f"Invalid parameters for '{skill_name}': {e}")
    except Exception as e:
        raise SkillError(f"Execution error: {e}")
