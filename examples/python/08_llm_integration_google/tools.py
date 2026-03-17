"""
Tool Definitions - Google A2A SDK Implementation

Tools that the LLM can call to perform actions.
Compatible with OpenAI Function Calling and Anthropic Tools.
"""

import json
import math
from typing import Dict, Any, Callable, List
from datetime import datetime


class ToolRegistry:
    """
    Registry of available tools for LLM function calling.
    
    Supports OpenAI and Anthropic tool formats.
    """
    
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.schemas: List[Dict] = []
        self._register_default_tools()
    
    def register(self, name: str, description: str, parameters: Dict):
        """
        Decorator to register a tool.
        
        Args:
            name: Tool name (used by LLM to call it)
            description: Tool description for LLM
            parameters: JSON Schema for tool parameters
        """
        def decorator(func: Callable):
            self.tools[name] = func
            self.schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters
                }
            })
            return func
        return decorator
    
    def execute(self, name: str, arguments: Dict) -> Any:
        """
        Execute a tool by name.
        
        Args:
            name: Tool name
            arguments: Tool arguments
            
        Returns:
            Tool execution result
        """
        if name not in self.tools:
            raise ValueError(f"Unknown tool: {name}")
        return self.tools[name](**arguments)
    
    def get_schemas(self) -> List[Dict]:
        """Get tool schemas for LLM API."""
        return self.schemas
    
    def _register_default_tools(self):
        """Register the default set of tools."""
        # These are registered via the decorator pattern
        pass


# Global tool registry instance
tools = ToolRegistry()


@tools.register(
    name="calculator",
    description="Perform mathematical calculations safely",
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Mathematical expression to evaluate (e.g., '25 * 47', 'sqrt(16)')"
            }
        },
        "required": ["expression"]
    }
)
def calculator(expression: str) -> str:
    """Safely evaluate a mathematical expression."""
    try:
        # Only allow safe operations
        allowed_names = {
            "abs": abs,
            "max": max,
            "min": min,
            "pow": pow,
            "round": round,
            "sqrt": math.sqrt,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "pi": math.pi,
            "e": math.e
        }
        
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


@tools.register(
    name="get_weather",
    description="Get current weather for a location (mock data)",
    parameters={
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "City name or coordinates"
            },
            "unit": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"],
                "description": "Temperature unit",
                "default": "celsius"
            }
        },
        "required": ["location"]
    }
)
def get_weather(location: str, unit: str = "celsius") -> str:
    """Get weather (mock implementation - replace with real API)."""
    temps = {"London": 15, "New York": 22, "Tokyo": 25, "Sydney": 28, "Paris": 18}
    temp = temps.get(location, 20)
    
    if unit == "fahrenheit":
        temp = temp * 9/5 + 32
        unit_symbol = "°F"
    else:
        unit_symbol = "°C"
    
    return f"Weather in {location}: {temp}{unit_symbol} (mock data - replace with real weather API)"


@tools.register(
    name="get_current_time",
    description="Get current date and time",
    parameters={
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "Timezone (e.g., 'UTC', 'America/New_York', 'Europe/London')",
                "default": "UTC"
            }
        }
    }
)
def get_current_time(timezone: str = "UTC") -> str:
    """Get current time."""
    now = datetime.now()
    return f"Current time ({timezone}): {now.strftime('%Y-%m-%d %H:%M:%S')}"


@tools.register(
    name="search_knowledge",
    description="Search knowledge base for information",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query to look up"
            }
        },
        "required": ["query"]
    }
)
def search_knowledge(query: str) -> str:
    """Search knowledge base (mock implementation)."""
    knowledge = {
        "a2a": "A2A (Agent-to-Agent) is Google's protocol for AI agents to communicate with each other.",
        "python": "Python is a high-level programming language known for readability and versatility.",
        "openai": "OpenAI is an AI research company that created GPT models and ChatGPT.",
        "anthropic": "Anthropic is an AI safety company that created the Claude family of models.",
        "llm": "LLM (Large Language Model) is a type of AI model trained on vast amounts of text data."
    }
    
    query_lower = query.lower()
    for key, value in knowledge.items():
        if key in query_lower:
            return value
    
    return f"No specific information found for '{query}'. Try asking about A2A, Python, OpenAI, Anthropic, or LLMs."


def handle_tool_calls(tool_calls: List[Dict], registry: ToolRegistry) -> List[Dict]:
    """
    Execute tool calls and return results.
    
    Args:
        tool_calls: List of tool call dicts from LLM
        registry: ToolRegistry instance to use
        
    Returns:
        List of tool results
    """
    results = []
    
    for call in tool_calls:
        name = call.get("name") or call.get("function", {}).get("name")
        arguments = call.get("arguments") or call.get("function", {}).get("arguments", {})
        tool_id = call.get("id", "")
        
        # Handle string arguments (OpenAI sends JSON string)
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        
        try:
            result = registry.execute(name, arguments)
            results.append({
                "tool_call_id": tool_id,
                "role": "tool",
                "name": name,
                "content": str(result)
            })
        except Exception as e:
            results.append({
                "tool_call_id": tool_id,
                "role": "tool",
                "name": name,
                "content": f"Error: {str(e)}"
            })
    
    return results
