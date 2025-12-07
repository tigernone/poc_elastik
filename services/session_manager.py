# services/session_manager.py
"""
Session Manager - Manage conversation state for "Tell me more"
Stores:
- User's original question
- Used source sentences
- Current level (0 → 1 → 2 → 3)
- Level offsets for pagination
- Extracted keywords
- History of used question variants (to avoid repetition)
"""
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field


@dataclass
class ConversationSession:
    """Store state of a conversation for multi-level retrieval"""
    session_id: str
    original_query: str  # User's original question
    
    # Multi-level tracking
    current_level: int = 0  # Current level (0 → 1 → 2 → 3)
    level_offsets: Dict[str, Any] = field(default_factory=lambda: {
        "0": 0,      # Level 0: combination index
        "1": 0,      # Level 1: keyword+magic index
        "2": 0,      # Level 2: synonym combinations index
        "3": 0,      # Level 3: synonym+magic index
        "4": 0       # Level 4: semantic vector offset (not paginated, kept for parity)
    })
    
    # Keywords and sentences
    keywords: List[str] = field(default_factory=list)  # Extracted clean keywords
    used_sentences: Set[str] = field(default_factory=set)  # Sentences already used
    used_sentence_ids: List[str] = field(default_factory=list)  # For JSON serialization
    
    # Question variants and meanings
    used_variants: List[str] = field(default_factory=list)  # Question variants already used
    previous_keywords: List[str] = field(default_factory=list)  # Keywords already explained
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    max_level_available: int = 20  # Max level (configurable for deep testing)
    continue_count: int = 0  # Number of times "Tell me more" was clicked
    
    def get_state_dict(self) -> Dict[str, Any]:
        """Get session state as dict for multi_level_retriever"""
        return {
            "current_level": self.current_level,
            "level_offsets": self.level_offsets,
            "used_sentence_ids": list(self.used_sentences)
        }
    
    def update_from_state(self, state: Dict[str, Any]):
        """Update session from state dict returned by retriever"""
        self.current_level = state.get("current_level", self.current_level)
        self.level_offsets = state.get("level_offsets", self.level_offsets)
        new_used = state.get("used_sentence_ids", [])
        self.used_sentences.update(new_used)
        self.used_sentence_ids = list(self.used_sentences)


class SessionManager:
    """
    Manage sessions in memory.
    For production, use Redis/DB.
    """
    
    def __init__(self, session_timeout_minutes: int = 30):
        self._sessions: Dict[str, ConversationSession] = {}
        self._timeout = timedelta(minutes=session_timeout_minutes)
    
    def create_session(
        self, 
        query: str, 
        max_level: int = 20,
        keywords: List[str] = None
    ) -> ConversationSession:
        """Create new session when user asks first question"""
        session_id = str(uuid.uuid4())
        session = ConversationSession(
            session_id=session_id,
            original_query=query,
            max_level_available=max_level,
            keywords=keywords or []
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
        increment_level: bool = False,
        state_dict: Dict[str, Any] = None
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
            session.continue_count += 1
        
        # Update from multi-level retriever state
        if state_dict:
            session.update_from_state(state_dict)
    
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
