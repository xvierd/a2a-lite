"""
Conversation Memory - Google A2A SDK Implementation

Manages multi-turn conversation history for LLM agents.
"""

import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Message:
    """A single message in the conversation history."""
    role: str  # system, user, assistant
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)


class ConversationManager:
    """
    Manages conversation sessions with memory.
    
    Features:
    - Session-based history (isolated per session_id)
    - Automatic trimming to prevent token overflow
    - Token estimation
    - Metadata storage per message
    - Session timeout/cleanup
    """
    
    def __init__(
        self,
        max_history: int = 10,
        max_tokens: int = 4000,
        session_timeout: int = 3600
    ):
        """
        Initialize conversation manager.
        
        Args:
            max_history: Maximum messages to keep per session
            max_tokens: Approximate token limit for history
            session_timeout: Session expiry time in seconds
        """
        self.max_history = max_history
        self.max_tokens = max_tokens
        self.session_timeout = session_timeout
        self.sessions: Dict[str, List[Message]] = defaultdict(list)
        self.last_access: Dict[str, float] = {}
    
    def get_or_create_session(self, session_id: str) -> List[Message]:
        """Get existing session or create a new one."""
        self._cleanup_expired()
        self.last_access[session_id] = time.time()
        return self.sessions[session_id]
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Add a message to the session.
        
        Args:
            session_id: Unique session identifier
            role: Message role (system/user/assistant/tool)
            content: Message content
            metadata: Optional metadata dict
        """
        message = Message(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        
        self.sessions[session_id].append(message)
        self.last_access[session_id] = time.time()
        
        # Trim if needed
        self._trim_session(session_id)
    
    def get_messages(
        self,
        session_id: str,
        include_system: bool = True
    ) -> List[Dict[str, str]]:
        """
        Get messages formatted for LLM API.
        
        Args:
            session_id: Session identifier
            include_system: Whether to include system messages
            
        Returns:
            List of message dicts with 'role' and 'content'
        """
        messages = []
        
        # Add system message if not present
        session = self.sessions[session_id]
        has_system = any(m.role == "system" for m in session)
        
        if not has_system:
            messages.append({
                "role": "system",
                "content": (
                    "You are a helpful AI assistant with access to tools. "
                    "You can use tools to perform calculations, get weather, "
                    "check time, and search knowledge. "
                    "When you need to use a tool, respond with a tool call."
                )
            })
        
        for msg in session:
            if msg.role == "system" and not include_system:
                continue
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        return messages
    
    def clear_session(self, session_id: str) -> None:
        """Clear a session's history."""
        if session_id in self.sessions:
            del self.sessions[session_id]
        if session_id in self.last_access:
            del self.last_access[session_id]
    
    def _trim_session(self, session_id: str) -> None:
        """Trim session to max_history while preserving system messages."""
        session = self.sessions[session_id]
        
        if len(session) <= self.max_history:
            return
        
        # Keep system messages
        system_messages = [m for m in session if m.role == "system"]
        other_messages = [m for m in session if m.role != "system"]
        
        # Keep most recent messages
        kept_messages = other_messages[-(self.max_history - len(system_messages)):]
        self.sessions[session_id] = system_messages + kept_messages
    
    def _cleanup_expired(self) -> None:
        """Remove expired sessions based on timeout."""
        now = time.time()
        expired = [
            sid for sid, last in self.last_access.items()
            if now - last > self.session_timeout
        ]
        for sid in expired:
            self.clear_session(sid)
    
    def estimate_tokens(self, session_id: str) -> int:
        """
        Estimate token count for a session.
        
        Uses rough estimate: ~4 characters per token.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Estimated token count
        """
        total_chars = sum(
            len(msg.content) for msg in self.sessions[session_id]
        )
        return total_chars // 4
