# services/session_manager.py
"""
Session Manager - Manage conversation state for "Tell me more"
Stores:
- User's original question
- Used source sentences
- Current level
- History of used question variants (to avoid repetition)
"""
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field


@dataclass
class ConversationSession:
    """Store state of a conversation"""
    session_id: str
    original_query: str  # User's original question
    current_level: int = 0  # Current level (starting from 0)
    used_sentences: Set[str] = field(default_factory=set)  # Sentences already used
    used_variants: List[str] = field(default_factory=list)  # Question variants already used
    previous_keywords: List[str] = field(default_factory=list)  # Keywords already explained
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    max_level_available: int = 0  # Highest level available in data
    continue_count: int = 0  # Number of times "Tell me more" was clicked


class SessionManager:
    """
    Manage sessions in memory.
    For production, use Redis/DB.
    """
    
    def __init__(self, session_timeout_minutes: int = 30):
        self._sessions: Dict[str, ConversationSession] = {}
        self._timeout = timedelta(minutes=session_timeout_minutes)
    
    def create_session(self, query: str, max_level: int = 0) -> ConversationSession:
        """Create new session when user asks first question"""
        session_id = str(uuid.uuid4())
        session = ConversationSession(
            session_id=session_id,
            original_query=query,
            max_level_available=max_level
        )
        self._sessions[session_id] = session
        self._cleanup_expired()
        return session
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get session by ID"""
        session = self._sessions.get(session_id)
        if session:
            # Check if expired
            if datetime.now() - session.last_accessed > self._timeout:
                del self._sessions[session_id]
                return None
            session.last_accessed = datetime.now()
        return session
    
    def update_session(
        self,
        session_id: str,
        used_sentences: List[str] = None,
        question_variants: str = None,
        keywords: str = None,
        increment_level: bool = False
    ):
        """Update session after each response"""
        session = self.get_session(session_id)
        if not session:
            return
        
        if used_sentences:
            session.used_sentences.update(used_sentences)
        
        if question_variants:
            session.used_variants.append(question_variants)
        
        if keywords:
            session.previous_keywords.append(keywords)
        
        if increment_level:
            session.current_level += 1
            session.continue_count += 1
    
    def can_continue(self, session_id: str) -> bool:
        """Check if can continue exploring deeper"""
        session = self.get_session(session_id)
        if not session:
            return False
        return session.current_level < session.max_level_available
    
    def delete_session(self, session_id: str):
        """Delete session"""
        if session_id in self._sessions:
            del self._sessions[session_id]
    
    def get_active_count(self) -> int:
        """Count active sessions"""
        self._cleanup_expired()
        return len(self._sessions)
    
    def clear_all(self):
        """Clear all sessions"""
        self._sessions.clear()
    
    def _cleanup_expired(self):
        """Clean up expired sessions"""
        now = datetime.now()
        expired = [
            sid for sid, sess in self._sessions.items()
            if now - sess.last_accessed > self._timeout
        ]
        for sid in expired:
            del self._sessions[sid]


# Global session manager instance
session_manager = SessionManager()
