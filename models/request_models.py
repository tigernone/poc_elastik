# models/request_models.py
"""
Request/Response Models with full Swagger documentation
"""
from pydantic import BaseModel, Field
from typing import Optional, List


# ============================================================
# REQUEST MODELS
# ============================================================

class AskRequest(BaseModel):
    """Request to ask a question"""
    query: str = Field(
        ...,
        description="User's question",
        min_length=1,
        max_length=2000,
        example="What are the duties of a class teacher?"
    )
    custom_prompt: Optional[str] = Field(
        None,
        description="Custom prompt/instructions from user (will be appended to the prompt)",
        max_length=1000,
        example="Please answer in bullet points. Focus on practical examples."
    )
    limit: Optional[int] = Field(
        15,
        description="Maximum number of source sentences to retrieve (default: 15)",
        ge=5,
        le=50,
        example=15
    )
    buffer_percentage: Optional[int] = Field(
        15,
        description="Buffer percentage for extra sentences (10-20%, default: 15%)",
        ge=10,
        le=20,
        example=15
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What are the duties of a class teacher?",
                "custom_prompt": "Please answer in bullet points.",
                "limit": 15,
                "buffer_percentage": 15
            }
        }


class ContinueRequest(BaseModel):
    """Request to continue and explore deeper (Tell me more)"""
    session_id: str = Field(
        ...,
        description="Session ID from /ask response",
        example="550e8400-e29b-41d4-a716-446655440000"
    )
    custom_prompt: Optional[str] = Field(
        None,
        description="Custom prompt/instructions for this continue request",
        max_length=1000,
        example="Focus more on specific regulations and rules."
    )
    limit: Optional[int] = Field(
        15,
        description="Maximum number of source sentences to retrieve",
        ge=5,
        le=50,
        example=15
    )
    buffer_percentage: Optional[int] = Field(
        15,
        description="Buffer percentage for extra sentences (10-20%)",
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
    """Settings for file upload"""
    sentences_per_level: Optional[int] = Field(
        5,
        description="Number of sentences per level (default: 5)",
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
    """A source sentence from the document"""
    text: str = Field(..., description="Sentence content")
    level: int = Field(..., description="Sentence level (0, 1, 2...)")
    score: float = Field(..., description="Similarity score with the query")
    sentence_index: Optional[int] = Field(None, description="Sentence index in original file")

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
    """Full response as per client requirements"""
    session_id: str = Field(
        ..., 
        description="Session ID to use for /continue (Tell me more)"
    )
    answer: str = Field(
        ..., 
        description="AI generated answer"
    )
    question_variants: str = Field(
        ..., 
        description="3-4 variants of the original question"
    )
    keyword_meaning: str = Field(
        ..., 
        description="Explanation of main keywords"
    )
    source_sentences: List[SourceSentence] = Field(
        ..., 
        description="List of source sentences used, grouped by level"
    )
    current_level: int = Field(
        ..., 
        description="Highest level used in this response"
    )
    max_level: int = Field(
        ..., 
        description="Highest level available in data"
    )
    prompt_used: str = Field(
        ..., 
        description="Full prompt sent to LLM (for debug/verify)"
    )
    can_continue: bool = Field(
        ..., 
        description="Can click 'Tell me more' to explore deeper"
    )
    sentences_retrieved: int = Field(
        ...,
        description="Actual number of sentences retrieved (after buffer applied)"
    )
    buffer_applied: int = Field(
        ...,
        description="Buffer percentage applied"
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
                "buffer_applied": 15
            }
        }


class ContinueResponse(BaseModel):
    """Response when user clicks Tell me more"""
    session_id: str = Field(..., description="Session ID")
    answer: str = Field(..., description="Expanded answer from AI")
    question_variants: str = Field(..., description="NEW question variants (no repeats)")
    keyword_meaning: str = Field(..., description="NEW/deeper keyword meanings")
    source_sentences: List[SourceSentence] = Field(..., description="Source sentences from deeper levels")
    current_level: int = Field(..., description="Current level")
    max_level: int = Field(..., description="Highest level available")
    prompt_used: str = Field(..., description="Full prompt sent")
    can_continue: bool = Field(..., description="Are there more levels to explore")
    continue_count: int = Field(..., description="Number of times Continue was clicked")
    sentences_retrieved: int = Field(..., description="Number of sentences retrieved")
    buffer_applied: int = Field(..., description="Buffer percentage applied")

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
                "buffer_applied": 15
            }
        }


class UploadResponse(BaseModel):
    """Response after successful file upload"""
    file_id: str = Field(..., description="Uploaded file ID")
    filename: str = Field(..., description="Original filename")
    total_sentences: int = Field(..., description="Total sentences processed")
    max_level: int = Field(..., description="Highest level (0 to max_level)")
    message: str = Field(..., description="Result message")
    buffer_info: Optional[str] = Field(None, description="Buffer capability information")

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
    """Document statistics in index"""
    total_documents: int = Field(..., description="Total documents")
    max_level: int = Field(..., description="Highest level")
    levels_available: int = Field(..., description="Number of levels available for Tell me more")
    ready: bool = Field(..., description="Ready to accept queries")

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
    status: str = Field(..., description="System status: healthy, degraded, unhealthy")
    elasticsearch: str = Field(..., description="Elasticsearch cluster status")
    elasticsearch_connected: bool = Field(..., description="ES connection successful")
    documents_indexed: int = Field(..., description="Number of indexed documents")
    active_sessions: int = Field(..., description="Number of active sessions")
    ready: bool = Field(..., description="Ready to serve queries")
    message: str = Field(..., description="Status message")

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
    detail: str = Field(..., description="Error details")
    error_code: Optional[str] = Field(None, description="Error code (if available)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "detail": "No documents found. Please upload a file first.",
                "error_code": "NO_DOCUMENTS"
            }
        }
