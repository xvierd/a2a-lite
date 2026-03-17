"""
LLM Client - Google A2A SDK Implementation

Integrates with REAL OpenAI and Anthropic APIs.
"""

import os
import json
from typing import List, Dict, Any, Optional, AsyncGenerator

# Try to import LLM libraries
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class LLMClient:
    """
    Client for LLM APIs (OpenAI and Anthropic).
    
    Supports:
    - Chat completions
    - Tool/function calling
    - Streaming responses
    """
    
    def __init__(self, provider: str = "openai", model: Optional[str] = None):
        """
        Initialize LLM client.
        
        Args:
            provider: "openai" or "anthropic"
            model: Model name (optional, uses default if not specified)
        """
        self.provider = provider.lower()
        
        if self.provider == "openai":
            if not OPENAI_AVAILABLE:
                raise ValueError("OpenAI package not installed. Run: pip install openai")
            
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable required")
            
            self.client = openai.AsyncOpenAI(api_key=api_key)
            self.model = model or "gpt-4"
            
        elif self.provider == "anthropic":
            if not ANTHROPIC_AVAILABLE:
                raise ValueError("Anthropic package not installed. Run: pip install anthropic")
            
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY environment variable required")
            
            self.client = anthropic.AsyncAnthropic(api_key=api_key)
            self.model = model or "claude-3-sonnet-20240229"
        else:
            raise ValueError(f"Unknown provider: {provider}. Use 'openai' or 'anthropic'")
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Send chat completion request.
        
        Args:
            messages: List of message dicts with role and content
            tools: Optional tool definitions for function calling
            temperature: Sampling temperature (0.0 - 2.0)
            stream: Whether to stream response (not fully implemented)
            
        Returns:
            Response dict with content and optional tool_calls
        """
        if self.provider == "openai":
            return await self._openai_chat(messages, tools, temperature, stream)
        else:
            return await self._anthropic_chat(messages, tools, temperature, stream)
    
    async def _openai_chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]],
        temperature: float,
        stream: bool
    ) -> Dict[str, Any]:
        """OpenAI chat completion implementation."""
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream
        }
        
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"
        
        if stream:
            # Return async generator for streaming
            return await self._openai_stream(params)
        
        response = await self.client.chat.completions.create(**params)
        
        message = response.choices[0].message
        result = {
            "content": message.content or "",
            "role": "assistant"
        }
        
        # Check for tool calls
        if message.tool_calls:
            result["tool_calls"] = [
                {
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                    "id": tc.id
                }
                for tc in message.tool_calls
            ]
        
        return result
    
    async def _openai_stream(self, params: Dict) -> AsyncGenerator[str, None]:
        """Stream OpenAI response (generator)."""
        stream = await self.client.chat.completions.create(**params)
        
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    async def _anthropic_chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]],
        temperature: float,
        stream: bool
    ) -> Dict[str, Any]:
        """Anthropic chat completion implementation."""
        # Separate system message from chat messages
        system_msg = None
        chat_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                chat_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        params = {
            "model": self.model,
            "messages": chat_messages,
            "temperature": temperature,
            "max_tokens": 4096
        }
        
        if system_msg:
            params["system"] = system_msg
        
        if tools:
            # Convert OpenAI tool format to Anthropic format
            anthropic_tools = []
            for tool in tools:
                if tool.get("type") == "function":
                    func = tool["function"]
                    anthropic_tools.append({
                        "name": func["name"],
                        "description": func["description"],
                        "input_schema": func["parameters"]
                    })
            params["tools"] = anthropic_tools
        
        if stream:
            return await self._anthropic_stream(params)
        
        response = await self.client.messages.create(**params)
        
        result = {
            "content": "",
            "role": "assistant"
        }
        
        # Extract content from response
        for content in response.content:
            if content.type == "text":
                result["content"] += content.text
            elif content.type == "tool_use":
                if "tool_calls" not in result:
                    result["tool_calls"] = []
                result["tool_calls"].append({
                    "name": content.name,
                    "arguments": content.input,
                    "id": content.id
                })
        
        return result
    
    async def _anthropic_stream(self, params: Dict) -> AsyncGenerator[str, None]:
        """Stream Anthropic response (generator)."""
        async with self.client.messages.stream(**params) as stream:
            async for text in stream.text_stream:
                yield text
