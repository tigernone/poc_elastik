# main.py
"""
AI Vector Search Demo (Elasticsearch)
=====================================
Full-featured Q&A system với:
- Multi-level retrieval (Level 0, 1, 2...)
- Structured prompt builder with custom prompts
- "Tell me more" functionality
- File management (upload with streaming, replace, delete)
- Buffer 10-20% for better retrieval
"""
import os
import uuid
from datetime import datetime
from typing import List
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from vector.elastic_client import init_index, es
from services.splitter import split_into_sentences
from services.retriever import (
    index_sentences, 
    index_sentences_batch,
    get_top_unique_sentences_grouped,
    get_sentences_by_level,
    get_max_level,
    delete_all_documents,
    get_document_count
)
from services.prompt_builder import (
    generate_question_variants,
    extract_keywords,
    build_final_prompt,
    call_llm,
)
from services.session_manager import session_manager
from models.request_models import (
    AskRequest, 
    AskResponse, 
    ContinueRequest, 
    ContinueResponse,
    UploadResponse,
    DocumentStats,
    HealthResponse,
    ErrorResponse
)

app = FastAPI(
    title="AI Vector Search Demo (Elasticsearch)",
    description="""
## 🤖 Hệ thống Q&A thông minh với Multi-level Retrieval

### 📋 Tổng quan
Hệ thống sử dụng Elasticsearch làm vector database, OpenAI cho embeddings và chat.
Hỗ trợ **7 modules chính** theo yêu cầu client:

### ✅ Các Modules:
1. **File Upload** - Upload file .txt với streaming (tránh tràn RAM)
2. **Sentence Embeddings** - Tạo vector embeddings cho từng câu
3. **Query Processing** - Xử lý câu hỏi với buffer 10-20%
4. **Deduplication** - Loại bỏ câu trùng lặp
5. **Prompt Builder** - Xây dựng prompt có cấu trúc + custom prompts
6. **Response Generation** - Sinh câu trả lời từ LLM
7. **"Tell me more"** - Đào sâu vào các levels tiếp theo

### 🔄 Flow hoạt động:
```
POST /upload → Tách câu → Embedding → Lưu ES (by level)
POST /ask → Vector search + Buffer → Prompt Builder → LLM → Response + session_id
POST /continue → Dùng session_id → Level tiếp theo → Expand answer
```

### 💡 Features nổi bật:
- **Buffer 10-20%**: Lấy thêm câu dự phòng để cải thiện kết quả
- **Custom Prompts**: Người dùng có thể thêm instructions riêng
- **Streaming Upload**: Đọc file theo chunks để tránh tràn RAM
- **Session Management**: Theo dõi cuộc hội thoại cho "Tell me more"
    """,
    version="2.0.0",
    openapi_tags=[
        {
            "name": "📁 File Management",
            "description": "Upload, replace, và quản lý documents trong Elasticsearch"
        },
        {
            "name": "❓ Q&A",
            "description": "Hỏi đáp với multi-level retrieval và custom prompts"
        },
        {
            "name": "📊 Info",
            "description": "Health check và thông tin hệ thống"
        }
    ],
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request"},
        404: {"model": ErrorResponse, "description": "Not Found"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)

# CORS cho dễ test từ frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Khởi tạo index khi app start
@app.on_event("startup")
def startup_event():
    init_index()


# ============================================================
# MODULE 1: File Management
# ============================================================

CHUNK_SIZE = 1024 * 1024  # 1MB chunks for streaming


@app.post(
    "/upload",
    response_model=UploadResponse,
    tags=["📁 File Management"],
    summary="Upload và index file .txt",
    description="""
## Upload file văn bản

### ⚙️ Xử lý:
1. **Streaming read** - Đọc file theo chunks (1MB) để tránh tràn RAM
2. **Sentence splitting** - Tách thành câu riêng lẻ
3. **Level assignment** - Mỗi 5 câu = 1 level
4. **Batch embedding** - Tạo embeddings theo batch (hiệu quả)
5. **Elasticsearch indexing** - Lưu vào vector database

### 📊 Kết quả trả về:
- `file_id`: ID duy nhất của file
- `filename`: Tên file gốc
- `total_sentences`: Số câu đã index
- `max_level`: Level cao nhất (để biết có bao nhiêu levels cho "Tell me more")
- `buffer_info`: Thông tin về khả năng buffer

### ⚠️ Lưu ý:
- Chỉ hỗ trợ file `.txt`
- Encoding: UTF-8 hoặc Latin-1 (auto-detect)
    """,
    responses={
        200: {
            "description": "File uploaded thành công",
            "content": {
                "application/json": {
                    "example": {
                        "file_id": "550e8400-e29b-41d4-a716-446655440000",
                        "filename": "document.txt",
                        "total_sentences": 50,
                        "max_level": 10,
                        "message": "File processed successfully. 50 sentences indexed across 11 levels."
                    }
                }
            }
        },
        400: {"description": "Invalid file type hoặc file rỗng"}
    }
)
async def upload_file(
    file: UploadFile = File(
        ..., 
        description="File .txt cần upload. Kích thước tối đa khuyến nghị: 10MB"
    )
):
    """
    Upload file .txt với streaming read để tối ưu RAM.
    
    File sẽ được:
    - Đọc theo chunks 1MB
    - Tách thành câu
    - Tạo embeddings theo batch
    - Index vào Elasticsearch với level
    """
    if not file.filename.endswith(".txt"):
        raise HTTPException(
            status_code=400, 
            detail="Only .txt files are supported. Please convert your document to .txt format."
        )

    # Streaming read để tránh tràn RAM với file lớn
    chunks = []
    total_size = 0
    MAX_SIZE = 50 * 1024 * 1024  # 50MB limit
    
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        chunks.append(chunk)
        total_size += len(chunk)
        
        if total_size > MAX_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size is 50MB. Your file: {total_size / (1024*1024):.1f}MB"
            )
    
    content_bytes = b"".join(chunks)
    
    try:
        text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = content_bytes.decode("latin-1")

    sentences = split_into_sentences(text)
    if not sentences:
        raise HTTPException(
            status_code=400, 
            detail="No valid sentences found in file. Make sure the file contains readable text."
        )

    # Index sentences với batch processing và lấy max_level
    file_id = str(uuid.uuid4())
    max_level = index_sentences_batch(sentences, file_id=file_id, batch_size=20)

    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        total_sentences=len(sentences),
        max_level=max_level,
        message=f"File processed successfully. {len(sentences)} sentences indexed across {max_level + 1} levels.",
        buffer_info=f"With 15% buffer, queries can retrieve up to {int(15 * 1.15)} sentences"
    )


@app.post(
    "/replace",
    response_model=UploadResponse,
    tags=["📁 File Management"],
    summary="Thay thế toàn bộ dữ liệu",
    description="""
## Thay thế dữ liệu hiện tại bằng file mới

### ⚙️ Xử lý:
1. **Xóa tất cả** documents cũ trong Elasticsearch
2. **Upload và index** file mới

### ⚠️ Cảnh báo:
- Hành động này KHÔNG THỂ hoàn tác
- Tất cả sessions hiện tại sẽ bị invalid
    """
)
async def replace_file(
    file: UploadFile = File(..., description="File .txt mới để thay thế")
):
    """Thay thế toàn bộ dữ liệu bằng file mới."""
    # Xóa dữ liệu cũ
    delete_all_documents()
    
    # Clear tất cả sessions
    session_manager.clear_all()
    
    # Upload file mới
    return await upload_file(file)


@app.delete(
    "/documents",
    tags=["📁 File Management"],
    summary="Xóa tất cả documents",
    description="""
## Xóa toàn bộ dữ liệu

### ⚠️ Cảnh báo:
- Hành động này KHÔNG THỂ hoàn tác
- Cần upload file mới trước khi sử dụng /ask
    """,
    responses={
        200: {
            "description": "Xóa thành công",
            "content": {
                "application/json": {
                    "example": {"message": "All documents deleted successfully", "documents_deleted": 50}
                }
            }
        }
    }
)
async def delete_all():
    """Xóa tất cả documents trong Elasticsearch."""
    count = get_document_count()
    success = delete_all_documents()
    session_manager.clear_all()
    
    if success:
        return {"message": "All documents deleted successfully", "documents_deleted": count}
    raise HTTPException(status_code=500, detail="Failed to delete documents")


@app.get(
    "/documents/count",
    response_model=DocumentStats,
    tags=["📁 File Management"],
    summary="Lấy thống kê documents",
    description="""
## Thống kê documents trong Elasticsearch

### 📊 Trả về:
- `total_documents`: Tổng số câu đã index
- `max_level`: Level cao nhất
- `levels_available`: Số levels có thể dùng cho "Tell me more"
- `ready`: True nếu có dữ liệu, sẵn sàng nhận câu hỏi
    """
)
async def get_count():
    """Lấy thống kê documents hiện có."""
    count = get_document_count()
    max_level = get_max_level()
    return DocumentStats(
        total_documents=count,
        max_level=max_level,
        levels_available=max_level + 1 if count > 0 else 0,
        ready=count > 0
    )


# ============================================================
# MODULE 2-6: Ask Question (First Query)
# ============================================================

@app.post(
    "/ask",
    response_model=AskResponse,
    tags=["❓ Q&A"],
    summary="Đặt câu hỏi",
    description="""
## Hỏi đáp với Multi-level Retrieval

### 🔄 Flow xử lý:
1. **Vector Search** - Tìm câu nguồn liên quan (với buffer 10-20%)
2. **Deduplicate** - Loại bỏ câu trùng lặp
3. **Generate Variants** - Tạo 3-4 biến thể câu hỏi
4. **Extract Keywords** - Giải nghĩa keywords quan trọng
5. **Build Prompt** - Xây dựng prompt có cấu trúc + custom instructions
6. **Call LLM** - Sinh câu trả lời

### 📥 Parameters:
- `query` (required): Câu hỏi của người dùng
- `limit`: Số câu nguồn tối đa (default: 15)
- `buffer_percentage`: % câu dự phòng (10-20%)
- `custom_prompt`: Instructions tùy chỉnh từ người dùng

### 📤 Response:
- `session_id`: Dùng cho /continue (Tell me more)
- `answer`: Câu trả lời từ LLM
- `source_sentences`: Các câu nguồn đã sử dụng
- `can_continue`: True nếu có thể đào sâu thêm

### 💡 Tips:
- Sử dụng `buffer_percentage=15` để cân bằng độ chính xác và độ đa dạng
- Thêm `custom_prompt` để điều chỉnh style/format câu trả lời
    """,
    responses={
        200: {
            "description": "Câu trả lời thành công",
            "content": {
                "application/json": {
                    "example": {
                        "session_id": "abc-123",
                        "answer": "Dựa trên thông tin tìm được...",
                        "question_variants": "1. What is X?\n2. Explain X...",
                        "source_sentences": [{"text": "Sample sentence", "level": 0, "score": 0.95}],
                        "current_level": 0,
                        "max_level": 5,
                        "can_continue": True
                    }
                }
            }
        }
    }
)
async def ask(req: AskRequest):
    """
    Nhận câu hỏi từ user, thực hiện full flow với buffer support.
    
    Hỗ trợ custom_prompt để người dùng có thể điều chỉnh
    cách LLM trả lời (format, style, language, etc.)
    """
    # Kiểm tra có data không
    if get_document_count() == 0:
        raise HTTPException(
            status_code=404, 
            detail="No documents found. Please upload a file first using POST /upload"
        )
    
    # 1. Lấy câu nguồn từ Elasticsearch với buffer support
    source_sentences = get_top_unique_sentences_grouped(
        req.query, 
        limit=req.limit,
        buffer_percentage=req.buffer_percentage
    )
    if not source_sentences:
        raise HTTPException(
            status_code=404, 
            detail="No source sentences found matching your query. Try rephrasing your question."
        )

    # 2. Tạo biến thể câu hỏi + giải nghĩa keyword
    question_variants = generate_question_variants(req.query)
    keyword_meaning = extract_keywords(req.query)

    # 3. Build final prompt với custom_prompt support

    # 3. Build final prompt với custom_prompt support
    prompt = build_final_prompt(
        user_query=req.query,
        question_variants=question_variants,
        keyword_meaning=keyword_meaning,
        source_sentences=source_sentences,
        continue_mode=False,
        custom_prompt=req.custom_prompt
    )

    # 4. Gọi LLM
    answer = call_llm(prompt)
    
    # 5. Tạo session để track conversation
    max_level = get_max_level()
    session = session_manager.create_session(req.query, max_level)
    
    # Cập nhật session với các câu đã dùng
    used_texts = [s["text"] for s in source_sentences]
    session_manager.update_session(
        session.session_id,
        used_sentences=used_texts,
        question_variants=question_variants,
        keywords=keyword_meaning
    )
    
    # Tính current_level từ source sentences
    current_level = max(s["level"] for s in source_sentences) if source_sentences else 0
    
    # Tính số câu thực tế được retrieve với buffer
    buffer_applied = req.buffer_percentage if req.buffer_percentage else 0

    return AskResponse(
        session_id=session.session_id,
        answer=answer,
        question_variants=question_variants,
        keyword_meaning=keyword_meaning,
        source_sentences=source_sentences,
        current_level=current_level,
        max_level=max_level,
        prompt_used=prompt,
        can_continue=current_level < max_level,
        sentences_retrieved=len(source_sentences),
        buffer_applied=buffer_applied
    )


# ============================================================
# MODULE 7: Continue / Tell me more
# ============================================================

@app.post(
    "/continue",
    response_model=ContinueResponse,
    tags=["❓ Q&A"],
    summary="Tell me more - Đào sâu thêm",
    description="""
## Mở rộng câu trả lời với thông tin từ levels sâu hơn

### 🔄 Flow xử lý:
1. **Get Session** - Lấy thông tin từ session_id
2. **Increase Level** - Chuyển sang Level 1, 2, 3...
3. **Get NEW sentences** - Lấy câu nguồn MỚI (exclude đã dùng)
4. **Generate NEW variants** - Tạo biến thể câu hỏi MỚI
5. **Update Keywords** - Bổ sung keywords mới
6. **Build Prompt** - Prompt cho chế độ continue + custom instructions
7. **Call LLM** - Sinh câu trả lời mở rộng

### 📥 Parameters:
- `session_id` (required): ID từ response của /ask
- `custom_prompt`: Instructions tùy chỉnh bổ sung
- `buffer_percentage`: % câu dự phòng (10-20%)

### 📤 Response:
- Tương tự /ask nhưng với thông tin từ levels sâu hơn
- `can_continue`: False khi đã hết levels

### 💡 Usage Pattern:
```
1. POST /ask → get session_id
2. POST /continue với session_id → get more info
3. Repeat POST /continue until can_continue=false
```
    """,
    responses={
        200: {"description": "Câu trả lời mở rộng thành công"},
        404: {"description": "Session không tồn tại hoặc đã hết hạn"},
        400: {"description": "Đã hết levels để đào sâu"}
    }
)
async def continue_conversation(req: ContinueRequest):
    """
    "Tell me more" - Đào sâu vào các level tiếp theo với buffer support.
    """
    # Lấy session
    session = session_manager.get_session(req.session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found or expired (30 min timeout). Please ask a new question with POST /ask"
        )
    
    # Kiểm tra có thể continue không
    if session.current_level >= session.max_level_available:
        raise HTTPException(
            status_code=400,
            detail="No more levels available. All information has been explored. Start a new question with POST /ask"
        )
    
    # Tăng level
    next_level = session.current_level + 1
    
    # Lấy câu nguồn từ level mới (exclude các câu đã dùng) với buffer
    source_sentences = get_sentences_by_level(
        query=session.original_query,
        start_level=next_level,
        limit=req.limit if req.limit else 15,
        exclude_texts=session.used_sentences,
        buffer_percentage=req.buffer_percentage
    )
    
    if not source_sentences:
        raise HTTPException(
            status_code=404,
            detail=f"No new sentences found at Level {next_level}. Try asking a different question."
        )
    
    # Tạo biến thể câu hỏi MỚI (không lặp với các lần trước)
    question_variants = generate_question_variants(
        session.original_query,
        previous_variants=session.used_variants,
        continue_mode=True
    )
    
    # Update keyword meaning (tìm keywords mới/sâu hơn)
    keyword_meaning = extract_keywords(
        session.original_query,
        previous_keywords=session.previous_keywords,
        continue_mode=True
    )
    
    # Build prompt mới với custom_prompt support
    prompt = build_final_prompt(
        user_query=session.original_query,
        question_variants=question_variants,
        keyword_meaning=keyword_meaning,
        source_sentences=source_sentences,
        continue_mode=True,
        continue_count=session.continue_count + 1,
        custom_prompt=req.custom_prompt
    )
    
    # Gọi LLM
    answer = call_llm(prompt)
    
    # Cập nhật session
    used_texts = [s["text"] for s in source_sentences]
    session_manager.update_session(
        session.session_id,
        used_sentences=used_texts,
        question_variants=question_variants,
        keywords=keyword_meaning,
        increment_level=True
    )
    
    # Tính current_level và buffer info
    current_level = max(s["level"] for s in source_sentences) if source_sentences else next_level
    buffer_applied = req.buffer_percentage if req.buffer_percentage else 0
    
    return ContinueResponse(
        session_id=session.session_id,
        answer=answer,
        question_variants=question_variants,
        keyword_meaning=keyword_meaning,
        source_sentences=source_sentences,
        current_level=current_level,
        max_level=session.max_level_available,
        prompt_used=prompt,
        can_continue=current_level < session.max_level_available,
        continue_count=session.continue_count + 1,
        sentences_retrieved=len(source_sentences),
        buffer_applied=buffer_applied
    )


# ============================================================
# Health & Info Endpoints
# ============================================================

@app.get(
    "/",
    tags=["📊 Info"],
    summary="Thông tin API",
    description="Trả về thông tin tổng quan về API và các endpoints"
)
async def root():
    """Thông tin tổng quan về API."""
    return {
        "message": "🤖 AI Vector Search Demo with Elasticsearch",
        "version": "2.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "features": [
            "✅ Multi-level retrieval (Level 0, 1, 2...)",
            "✅ Structured prompt builder",
            "✅ Custom prompts support",
            "✅ Buffer 10-20% for better retrieval",
            "✅ Tell me more functionality",
            "✅ Streaming file upload",
            "✅ File management"
        ],
        "endpoints": {
            "file_management": {
                "POST /upload": "Upload file .txt (streaming)",
                "POST /replace": "Thay thế toàn bộ dữ liệu",
                "DELETE /documents": "Xóa tất cả",
                "GET /documents/count": "Thống kê documents"
            },
            "qa": {
                "POST /ask": "Hỏi câu hỏi → nhận session_id",
                "POST /continue": "Tell me more với session_id"
            }
        },
        "quick_start": [
            "1. POST /upload với file .txt",
            "2. POST /ask với query và optional custom_prompt",
            "3. POST /continue với session_id để đào sâu"
        ]
    }


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["📊 Info"],
    summary="Health check",
    description="""
## Kiểm tra trạng thái hệ thống

### Kiểm tra:
- Elasticsearch connection
- Documents count
- Active sessions

### Status codes:
- `healthy`: Hệ thống hoạt động bình thường
- `degraded`: Có vấn đề nhưng vẫn hoạt động
- `unhealthy`: Hệ thống không hoạt động
    """
)
async def health():
    """Health check endpoint với chi tiết về ES và sessions."""
    try:
        # Check Elasticsearch
        es_health = es.cluster.health()
        es_status = es_health["status"]
        es_connected = True
    except Exception as e:
        es_status = f"error: {str(e)}"
        es_connected = False
    
    doc_count = get_document_count()
    active_sessions = session_manager.get_active_count()
    
    # Determine overall status
    if es_connected and doc_count > 0:
        status = "healthy"
    elif es_connected:
        status = "degraded"
    else:
        status = "unhealthy"
    
    return HealthResponse(
        status=status,
        elasticsearch=es_status,
        elasticsearch_connected=es_connected,
        documents_indexed=doc_count,
        active_sessions=active_sessions,
        ready=doc_count > 0,
        message="Upload a file with POST /upload to get started" if doc_count == 0 else "System ready for queries"
    )
