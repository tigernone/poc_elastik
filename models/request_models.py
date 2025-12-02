# models/request_models.py
"""
Request/Response Models với đầy đủ documentation cho Swagger
"""
from pydantic import BaseModel, Field
from typing import Optional, List


# ============================================================
# REQUEST MODELS
# ============================================================

class AskRequest(BaseModel):
    """Request để hỏi câu hỏi"""
    query: str = Field(
        ...,
        description="Câu hỏi của user",
        min_length=1,
        max_length=2000,
        example="What are the duties of a class teacher?"
    )
    custom_prompt: Optional[str] = Field(
        None,
        description="Custom prompt/instructions từ user (sẽ được thêm vào cuối prompt)",
        max_length=1000,
        example="Please answer in bullet points. Focus on practical examples."
    )
    limit: Optional[int] = Field(
        15,
        description="Số câu nguồn tối đa cần lấy (mặc định 15)",
        ge=5,
        le=50,
        example=15
    )
    buffer_percentage: Optional[int] = Field(
        15,
        description="Buffer % thêm khi lấy câu (10-20%, mặc định 15%)",
        ge=10,
        le=20,
        example=15
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What are the duties of a class teacher?",
                "custom_prompt": "Please answer in Vietnamese. Use bullet points.",
                "limit": 15,
                "buffer_percentage": 15
            }
        }


class ContinueRequest(BaseModel):
    """Request để tiếp tục đào sâu câu trả lời (Tell me more)"""
    session_id: str = Field(
        ...,
        description="Session ID từ response của /ask",
        example="550e8400-e29b-41d4-a716-446655440000"
    )
    custom_prompt: Optional[str] = Field(
        None,
        description="Custom prompt/instructions cho lần continue này",
        max_length=1000,
        example="Focus more on specific regulations and rules."
    )
    limit: Optional[int] = Field(
        15,
        description="Số câu nguồn tối đa cần lấy",
        ge=5,
        le=50,
        example=15
    )
    buffer_percentage: Optional[int] = Field(
        15,
        description="Buffer % thêm khi lấy câu (10-20%)",
        ge=10,
        le=20,
        example=15
    )

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "custom_prompt": "Give me more practical examples",
                "limit": 15,
                "buffer_percentage": 15
            }
        }


class UploadSettings(BaseModel):
    """Settings cho upload file"""
    sentences_per_level: Optional[int] = Field(
        5,
        description="Số câu mỗi level (mặc định 5)",
        ge=1,
        le=20,
        example=5
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "sentences_per_level": 5
            }
        }


# ============================================================
# RESPONSE MODELS
# ============================================================

class SourceSentence(BaseModel):
    """Một câu nguồn từ tài liệu"""
    text: str = Field(..., description="Nội dung câu")
    level: int = Field(..., description="Level của câu (0, 1, 2...)")
    score: float = Field(..., description="Điểm similarity với câu hỏi")
    sentence_index: Optional[int] = Field(None, description="Thứ tự câu trong file gốc")

    class Config:
        json_schema_extra = {
            "example": {
                "text": "The class teacher is responsible for maintaining discipline.",
                "level": 0,
                "score": 1.85,
                "sentence_index": 12
            }
        }


class AskResponse(BaseModel):
    """Response đầy đủ theo yêu cầu khách hàng"""
    session_id: str = Field(
        ..., 
        description="ID session để dùng cho /continue (Tell me more)"
    )
    answer: str = Field(
        ..., 
        description="Câu trả lời từ AI"
    )
    question_variants: str = Field(
        ..., 
        description="3-4 biến thể của câu hỏi gốc"
    )
    keyword_meaning: str = Field(
        ..., 
        description="Giải nghĩa các keywords chính"
    )
    source_sentences: List[SourceSentence] = Field(
        ..., 
        description="Danh sách câu nguồn đã dùng, group theo level"
    )
    current_level: int = Field(
        ..., 
        description="Level cao nhất đã sử dụng trong lần trả lời này"
    )
    max_level: int = Field(
        ..., 
        description="Level cao nhất có sẵn trong dữ liệu"
    )
    prompt_used: str = Field(
        ..., 
        description="Full prompt đã gửi cho LLM (để debug/verify)"
    )
    can_continue: bool = Field(
        ..., 
        description="Có thể bấm 'Tell me more' để đào sâu thêm không"
    )
    sentences_retrieved: int = Field(
        ...,
        description="Số câu thực tế đã lấy (sau khi áp dụng buffer)"
    )
    buffer_applied: int = Field(
        ...,
        description="Buffer % đã áp dụng"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "answer": "The class teacher has several key responsibilities...",
                "question_variants": "1. What responsibilities does a class teacher have?\n2. Can you explain the role of a class teacher?\n3. What are the main duties assigned to class teachers?",
                "keyword_meaning": "Class teacher refers to the primary teacher responsible for a specific class. Duties include academic guidance, discipline management, and parent communication.",
                "source_sentences": [
                    {"text": "The class teacher must maintain discipline.", "level": 0, "score": 1.85, "sentence_index": 12}
                ],
                "current_level": 1,
                "max_level": 43,
                "prompt_used": "[Full prompt here...]",
                "can_continue": True,
                "sentences_retrieved": 17,
                "buffer_applied": "15%"
            }
        }


class ContinueResponse(BaseModel):
    """Response khi user bấm Tell me more"""
    session_id: str = Field(..., description="Session ID")
    answer: str = Field(..., description="Câu trả lời mở rộng từ AI")
    question_variants: str = Field(..., description="Biến thể câu hỏi MỚI (không lặp)")
    keyword_meaning: str = Field(..., description="Keyword meaning MỚI/sâu hơn")
    source_sentences: List[SourceSentence] = Field(..., description="Câu nguồn từ level sâu hơn")
    current_level: int = Field(..., description="Level hiện tại")
    max_level: int = Field(..., description="Level cao nhất có sẵn")
    prompt_used: str = Field(..., description="Full prompt đã gửi")
    can_continue: bool = Field(..., description="Còn level để đi sâu không")
    continue_count: int = Field(..., description="Số lần đã bấm Continue")
    sentences_retrieved: int = Field(..., description="Số câu đã lấy")
    buffer_applied: int = Field(..., description="Buffer % đã áp dụng")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "answer": "Additionally, the class teacher should also...",
                "question_variants": "1. What other aspects should we explore?\n2. Are there more specific duties?",
                "keyword_meaning": "Further aspects include administrative duties and student counseling.",
                "source_sentences": [
                    {"text": "In addition to teaching...", "level": 2, "score": 1.68, "sentence_index": 45}
                ],
                "current_level": 2,
                "max_level": 43,
                "prompt_used": "[Full prompt here...]",
                "can_continue": True,
                "continue_count": 1,
                "sentences_retrieved": 17,
                "buffer_applied": "15%"
            }
        }


class UploadResponse(BaseModel):
    """Response sau khi upload file thành công"""
    file_id: str = Field(..., description="ID của file đã upload")
    filename: str = Field(..., description="Tên file gốc")
    total_sentences: int = Field(..., description="Tổng số câu đã xử lý")
    max_level: int = Field(..., description="Level cao nhất (0 đến max_level)")
    message: str = Field(..., description="Thông báo kết quả")
    buffer_info: Optional[str] = Field(None, description="Thông tin về buffer capability")

    class Config:
        json_schema_extra = {
            "example": {
                "file_id": "abc-123-def",
                "filename": "school_rules.txt",
                "total_sentences": 220,
                "max_level": 43,
                "message": "File processed successfully. 220 sentences indexed across 44 levels.",
                "buffer_info": "With 15% buffer, queries can retrieve up to 17 sentences"
            }
        }


class DocumentStats(BaseModel):
    """Thống kê documents trong index"""
    total_documents: int = Field(..., description="Tổng số documents")
    max_level: int = Field(..., description="Level cao nhất")
    levels_available: int = Field(..., description="Số levels có sẵn cho Tell me more")
    ready: bool = Field(..., description="Sẵn sàng để query")

    class Config:
        json_schema_extra = {
            "example": {
                "total_documents": 220,
                "max_level": 43,
                "levels_available": 44,
                "ready": True
            }
        }


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(..., description="Trạng thái hệ thống: healthy, degraded, unhealthy")
    elasticsearch: str = Field(..., description="Trạng thái Elasticsearch cluster")
    elasticsearch_connected: bool = Field(..., description="Kết nối ES thành công")
    documents_indexed: int = Field(..., description="Số documents đã index")
    active_sessions: int = Field(..., description="Số sessions đang hoạt động")
    ready: bool = Field(..., description="Sẵn sàng phục vụ queries")
    message: str = Field(..., description="Thông báo trạng thái")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "elasticsearch": "green",
                "elasticsearch_connected": True,
                "documents_indexed": 220,
                "active_sessions": 5,
                "ready": True,
                "message": "System ready for queries"
            }
        }


class ErrorResponse(BaseModel):
    """Error response format"""
    detail: str = Field(..., description="Chi tiết lỗi")
    error_code: Optional[str] = Field(None, description="Mã lỗi (nếu có)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "detail": "No documents found. Please upload a file first.",
                "error_code": "NO_DOCUMENTS"
            }
        }
