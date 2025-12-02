# main.py
"""
AI Vector Search Demo (Elasticsearch)
=====================================
Full-featured Q&A system with:
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
## 🤖 Intelligent Q&A System with Multi-level Retrieval

### 📋 Overview
This system uses Elasticsearch as a vector database, OpenAI for embeddings and chat.
Supports **7 main modules** as per client requirements:

### ✅ Modules:
1. **File Upload** - Upload .txt files with streaming (prevents RAM overflow)
2. **Sentence Embeddings** - Create vector embeddings for each sentence
3. **Query Processing** - Process queries with 10-20% buffer
4. **Deduplication** - Remove duplicate sentences
5. **Prompt Builder** - Build structured prompts + custom prompts
6. **Response Generation** - Generate answers from LLM
7. **"Tell me more"** - Dive deeper into subsequent levels

### 🔄 Workflow:
```
POST /upload → Split sentences → Embedding → Store in ES (by level)
POST /ask → Vector search + Buffer → Prompt Builder → LLM → Response + session_id
POST /continue → Use session_id → Next level → Expand answer
```

### 💡 Key Features:
- **Buffer 10-20%**: Retrieve extra sentences to improve results
- **Custom Prompts**: Users can add their own instructions
- **Streaming Upload**: Read files in chunks to prevent RAM overflow
- **Session Management**: Track conversations for "Tell me more"
    """,
    version="2.0.0",
    openapi_tags=[
        {
            "name": "📁 File Management",
            "description": "Upload, replace, and manage documents in Elasticsearch"
        },
        {
            "name": "❓ Q&A",
            "description": "Q&A with multi-level retrieval and custom prompts"
        },
        {
            "name": "📊 Info",
            "description": "Health check and system information"
        }
    ],
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request"},
        404: {"model": ErrorResponse, "description": "Not Found"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)

# CORS for easy frontend testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Initialize index on app startup
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
    summary="Upload and index .txt file",
    description="""
## Upload Text File

### ⚙️ Processing:
1. **Streaming read** - Read file in chunks (1MB) to prevent RAM overflow
2. **Sentence splitting** - Split into individual sentences
3. **Level assignment** - Every 5 sentences = 1 level
4. **Batch embedding** - Create embeddings in batches (efficient)
5. **Elasticsearch indexing** - Store in vector database

### 📊 Response:
- `file_id`: Unique file ID
- `filename`: Original filename
- `total_sentences`: Number of indexed sentences
- `max_level`: Highest level (indicates how many levels for "Tell me more")
- `buffer_info`: Buffer capability information

### ⚠️ Notes:
- Only `.txt` files supported
- Encoding: UTF-8 or Latin-1 (auto-detect)
    """,
    responses={
        200: {
            "description": "File uploaded successfully",
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
        400: {"description": "Invalid file type or empty file"}
    }
)
async def upload_file(
    file: UploadFile = File(
        ..., 
        description="The .txt file to upload. Recommended max size: 10MB"
    )
):
    """
    Upload .txt file with streaming read for RAM optimization.
    """
    if not file.filename.endswith(".txt"):
        raise HTTPException(
            status_code=400, 
            detail="Only .txt files are supported. Please convert your document to .txt format."
        )

    # Streaming read to prevent RAM overflow with large files
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

    # Index sentences with batch processing
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
    summary="Replace all data",
    description="""
## Replace Current Data with New File

### ⚙️ Processing:
1. **Delete all** old documents in Elasticsearch
2. **Upload and index** new file

### ⚠️ Warning:
- This action CANNOT be undone
- All current sessions will be invalidated
    """
)
async def replace_file(
    file: UploadFile = File(..., description="New .txt file to replace current data")
):
    """Replace all data with new file."""
    delete_all_documents()
    session_manager.clear_all()
    return await upload_file(file)


@app.delete(
    "/documents",
    tags=["📁 File Management"],
    summary="Delete all documents",
    description="""
## Delete All Data

### ⚠️ Warning:
- This action CANNOT be undone
- You need to upload a new file before using /ask
    """,
    responses={
        200: {
            "description": "Deleted successfully",
            "content": {
                "application/json": {
                    "example": {"message": "All documents deleted successfully", "documents_deleted": 50}
                }
            }
        }
    }
)
async def delete_all():
    """Delete all documents in Elasticsearch."""
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
    summary="Get document statistics",
    description="""
## Document Statistics in Elasticsearch

### 📊 Returns:
- `total_documents`: Total indexed sentences
- `max_level`: Highest level
- `levels_available`: Number of levels for "Tell me more"
- `ready`: True if data exists, ready to accept queries
    """
)
async def get_count():
    """Get current document statistics."""
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
    summary="Ask a question",
    description="""
## Q&A with Multi-level Retrieval

### 🔄 Processing Flow:
1. **Vector Search** - Find relevant source sentences (with 10-20% buffer)
2. **Deduplicate** - Remove duplicate sentences
3. **Generate Variants** - Create 3-4 question variants
4. **Extract Keywords** - Extract and explain important keywords
5. **Build Prompt** - Build structured prompt + custom instructions
6. **Call LLM** - Generate answer

### 📥 Parameters:
- `query` (required): User's question
- `limit`: Maximum source sentences (default: 15)
- `buffer_percentage`: Extra sentences percentage (10-20%)
- `custom_prompt`: User's custom instructions

### 📤 Response:
- `session_id`: Use for /continue (Tell me more)
- `answer`: LLM's answer
- `source_sentences`: Source sentences used
- `can_continue`: True if can explore deeper

### 💡 Tips:
- Use `buffer_percentage=15` for balance between accuracy and diversity
- Add `custom_prompt` to adjust answer style/format
    """,
    responses={
        200: {
            "description": "Answer generated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "session_id": "abc-123",
                        "answer": "Based on the information found...",
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
    Receive user question and execute full flow with buffer support.
    """
    # Check if data exists
    if get_document_count() == 0:
        raise HTTPException(
            status_code=404, 
            detail="No documents found. Please upload a file first using POST /upload"
        )
    
    # 1. Get source sentences from Elasticsearch with buffer support
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

    # 2. Generate question variants + extract keywords
    question_variants = generate_question_variants(req.query)
    keyword_meaning = extract_keywords(req.query)

    # 3. Build final prompt with custom_prompt support
    prompt = build_final_prompt(
        user_query=req.query,
        question_variants=question_variants,
        keyword_meaning=keyword_meaning,
        source_sentences=source_sentences,
        continue_mode=False,
        custom_prompt=req.custom_prompt
    )

    # 4. Call LLM
    answer = call_llm(prompt)
    
    # 5. Create session to track conversation
    max_level = get_max_level()
    session = session_manager.create_session(req.query, max_level)
    
    # Update session with used sentences
    used_texts = [s["text"] for s in source_sentences]
    session_manager.update_session(
        session.session_id,
        used_sentences=used_texts,
        question_variants=question_variants,
        keywords=keyword_meaning
    )
    
    # Calculate current_level from source sentences
    current_level = max(s["level"] for s in source_sentences) if source_sentences else 0
    
    # Calculate buffer applied
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
    summary="Tell me more - Explore deeper",
    description="""
## Expand Answer with Information from Deeper Levels

### 🔄 Processing Flow:
1. **Get Session** - Retrieve info from session_id
2. **Increase Level** - Move to Level 1, 2, 3...
3. **Get NEW sentences** - Get NEW source sentences (exclude used ones)
4. **Generate NEW variants** - Create NEW question variants
5. **Update Keywords** - Add new keywords
6. **Build Prompt** - Prompt for continue mode + custom instructions
7. **Call LLM** - Generate expanded answer

### 📥 Parameters:
- `session_id` (required): ID from /ask response
- `custom_prompt`: Additional custom instructions
- `buffer_percentage`: Extra sentences percentage (10-20%)

### 📤 Response:
- Similar to /ask but with info from deeper levels
- `can_continue`: False when all levels explored

### 💡 Usage Pattern:
```
1. POST /ask → get session_id
2. POST /continue with session_id → get more info
3. Repeat POST /continue until can_continue=false
```
    """,
    responses={
        200: {"description": "Expanded answer generated successfully"},
        404: {"description": "Session not found or expired"},
        400: {"description": "No more levels to explore"}
    }
)
async def continue_conversation(req: ContinueRequest):
    """
    "Tell me more" - Explore deeper levels with buffer support.
    """
    # Get session
    session = session_manager.get_session(req.session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found or expired (30 min timeout). Please ask a new question with POST /ask"
        )
    
    # Check if can continue
    if session.current_level >= session.max_level_available:
        raise HTTPException(
            status_code=400,
            detail="No more levels available. All information has been explored. Start a new question with POST /ask"
        )
    
    # Increase level
    next_level = session.current_level + 1
    
    # Get source sentences from new level (exclude used ones) with buffer
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
    
    # Generate NEW question variants (don't repeat previous ones)
    question_variants = generate_question_variants(
        session.original_query,
        previous_variants=session.used_variants,
        continue_mode=True
    )
    
    # Update keyword meaning (find new/deeper keywords)
    keyword_meaning = extract_keywords(
        session.original_query,
        previous_keywords=session.previous_keywords,
        continue_mode=True
    )
    
    # Build new prompt with custom_prompt support
    prompt = build_final_prompt(
        user_query=session.original_query,
        question_variants=question_variants,
        keyword_meaning=keyword_meaning,
        source_sentences=source_sentences,
        continue_mode=True,
        continue_count=session.continue_count + 1,
        custom_prompt=req.custom_prompt
    )
    
    # Call LLM
    answer = call_llm(prompt)
    
    # Update session
    used_texts = [s["text"] for s in source_sentences]
    session_manager.update_session(
        session.session_id,
        used_sentences=used_texts,
        question_variants=question_variants,
        keywords=keyword_meaning,
        increment_level=True
    )
    
    # Calculate current_level and buffer info
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
    summary="API Information",
    description="Returns overview information about the API and endpoints"
)
async def root():
    """API overview information."""
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
                "POST /upload": "Upload .txt file (streaming)",
                "POST /replace": "Replace all data",
                "DELETE /documents": "Delete all",
                "GET /documents/count": "Get document statistics"
            },
            "qa": {
                "POST /ask": "Ask question → get session_id",
                "POST /continue": "Tell me more with session_id"
            }
        },
        "quick_start": [
            "1. POST /upload with .txt file",
            "2. POST /ask with query and optional custom_prompt",
            "3. POST /continue with session_id to explore deeper"
        ]
    }


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["📊 Info"],
    summary="Health check",
    description="""
## Check System Status

### Checks:
- Elasticsearch connection
- Documents count
- Active sessions

### Status codes:
- `healthy`: System operating normally
- `degraded`: Issues but still operational
- `unhealthy`: System not operational
    """
)
async def health():
    """Health check endpoint with ES and session details."""
    try:
        es_health = es.cluster.health()
        es_status = es_health["status"]
        es_connected = True
    except Exception as e:
        es_status = f"error: {str(e)}"
        es_connected = False
    
    doc_count = get_document_count()
    active_sessions = session_manager.get_active_count()
    
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
