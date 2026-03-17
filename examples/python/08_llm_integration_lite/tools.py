"""
Tool Definitions for LLM Agent

Simple tool implementations that the LLM can call.
"""

import math
from datetime import datetime
from a2a_lite.tools import tool


@tool(description="Perform mathematical calculations")
def calculator(expression: str) -> str:
    """
    Safely evaluate a mathematical expression.
    
    Args:
        expression: Math expression like "25 * 47" or "sqrt(16)"
    """
    try:
        allowed = {
            "abs": abs, "max": max, "min": min,
            "pow": pow, "sqrt": math.sqrt,
            "sin": math.sin, "cos": math.cos,
            "pi": math.pi, "e": math.e
        }
        result = eval(expression, {"__builtins__": {}}, allowed)
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {e}"


@tool(description="Get current date and time")
def get_current_time(timezone: str = "UTC") -> str:
    """Get the current time."""
    now = datetime.now()
    return f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}"


@tool(description="Get weather information")
def get_weather(location: str, unit: str = "celsius") -> str:
    """
    Get weather for a location.
    
    Args:
        location: City name
        unit: celsius or fahrenheit
    """
    # Mock implementation
    temps = {"London": 15, "New York": 22, "Tokyo": 25}
    temp = temps.get(location, 20)
    
    if unit == "fahrenheit":
        temp = temp * 9/5 + 32
        return f"{location}: {temp}°F"
    return f"{location}: {temp}°C"


@tool(description="Search knowledge base")
def search(query: str) -> str:
    """Search for information."""
    knowledge = {
        "a2a": "A2A is Google's Agent-to-Agent protocol.",
        "python": "Python is a popular programming language.",
        "llm": "LLM stands for Large Language Model."
    }
    
    query_lower = query.lower()
    for key, value in knowledge.items():
        if key in query_lower:
            return value
    
    return f"No specific info about '{query}'"
