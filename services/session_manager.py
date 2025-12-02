# services/session_manager.py
"""
Session Manager - Quản lý trạng thái conversation cho "Tell me more"
Lưu trữ:
- Câu hỏi gốc của user
- Các câu nguồn đã sử dụng
- Level hiện tại đang ở
- Lịch sử các question variants đã dùng (để không lặp)
"""
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field


@dataclass
class ConversationSession:
    """Lưu trạng thái của một conversation"""
    session_id: str
    original_query: str  # Câu hỏi gốc của user
    current_level: int = 0  # Level hiện tại (bắt đầu từ 0)
    used_sentences: Set[str] = field(default_factory=set)  # Các câu đã dùng
    used_variants: List[str] = field(default_factory=list)  # Các biến thể câu hỏi đã dùng
    previous_keywords: List[str] = field(default_factory=list)  # Keywords đã giải nghĩa
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    max_level_available: int = 0  # Level cao nhất có sẵn trong data
    continue_count: int = 0  # Số lần đã bấm "Tell me more"


class SessionManager:
    """
    Quản lý sessions trong memory.
    Production nên dùng Redis/DB.
    """
    
    def __init__(self, session_timeout_minutes: int = 30):
        self._sessions: Dict[str, ConversationSession] = {}
        self._timeout = timedelta(minutes=session_timeout_minutes)
    
    def create_session(self, query: str, max_level: int = 0) -> ConversationSession:
        """Tạo session mới khi user hỏi câu hỏi đầu tiên"""
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
        """Lấy session theo ID"""
        session = self._sessions.get(session_id)
        if session:
            # Kiểm tra hết hạn
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
        """Cập nhật session sau mỗi lần trả lời"""
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
        """Kiểm tra xem có thể tiếp tục đào sâu không"""
        session = self.get_session(session_id)
        if not session:
            return False
        return session.current_level < session.max_level_available
    
    def delete_session(self, session_id: str):
        """Xóa session"""
        if session_id in self._sessions:
            del self._sessions[session_id]
    
    def get_active_count(self) -> int:
        """Đếm số sessions đang hoạt động"""
        self._cleanup_expired()
        return len(self._sessions)
    
    def clear_all(self):
        """Xóa tất cả sessions"""
        self._sessions.clear()
    
    def _cleanup_expired(self):
        """Dọn dẹp các session hết hạn"""
        now = datetime.now()
        expired = [
            sid for sid, sess in self._sessions.items()
            if now - sess.last_accessed > self._timeout
        ]
        for sid in expired:
            del self._sessions[sid]


# Global session manager instance
session_manager = SessionManager()
