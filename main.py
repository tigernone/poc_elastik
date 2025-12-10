# main.py
"""
AI Vector Search Demo (Elasticsearch)
=====================================
Full-featured Q&A system with:
- Multi-level retrieval (Level 0 → 1 → 2 → 3)
  - Level 0: Keyword combinations
  - Level 1: Single keywords
  - Level 2: Synonyms
  - Level 3: Keyword + Magical words
- Structured prompt builder with custom prompts
- "Tell me more" functionality with progressive exploration
- File management (upload with streaming, replace, delete)
- Buffer 10-20% for better retrieval
"""
import os
import uuid
import logging
from datetime import datetime
from typing import List
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import ClientDisconnect
import asyncio
import signal
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
from services.keyword_extractor import (
    extract_keywords as extract_clean_keywords,
    get_magical_words_for_level3,
    generate_synonyms,
)
from services.multi_level_retriever import get_next_batch, MultiLevelRetriever
from services.biblical_parallels import (
    analyze_biblical_parallels,
    gather_biblical_parallels_sentences,
)
from services.deduplicator import deduplicate_sentences
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

# Request size limit middleware
class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")
            if content_length:
                if int(content_length) > settings.MAX_REQUEST_SIZE:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": f"Request body too large. Maximum size is {settings.MAX_REQUEST_SIZE / (1024*1024):.1f}MB"
                        }
                    )
        
        try:
            response = await call_next(request)
            return response
        except ClientDisconnect:
            logger.warning("Client disconnected during request")
            return JSONResponse(
                status_code=499,
                content={"detail": "Client disconnected"}
            )
        except Exception as e:
            logger.error(f"Unexpected error in middleware: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error. Please try again."}
            )

# Timeout middleware
class TimeoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Different timeouts for different endpoints
        timeout = settings.REQUEST_TIMEOUT
        if "/upload" in request.url.path:
            timeout = settings.UPLOAD_TIMEOUT
        
        try:
            response = await asyncio.wait_for(
                call_next(request),
                timeout=timeout
            )
            return response
        except asyncio.TimeoutError:
            logger.error(f"Request timeout after {timeout}s: {request.url.path}")
            return JSONResponse(
                status_code=504,
                content={"detail": f"Request timeout after {timeout} seconds. Please try with smaller data or simpler query."}
            )
        except Exception as e:
            logger.error(f"Error in timeout middleware: {str(e)}")
            raise

# Add middlewares
app.add_middleware(TimeoutMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)

# CORS for easy frontend testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global shutdown flag
shutdown_flag = False

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global shutdown_flag
    logger.info(f"Received signal {signum}. Initiating graceful shutdown...")
    shutdown_flag = True
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# Initialize index on app startup
@app.on_event("startup")
async def startup_event():
    try:
        init_index()
        logger.info("✓ Elasticsearch index initialized")
    except Exception as e:
        logger.error(f"Warning: Could not initialize Elasticsearch index: {e}")
        logger.warning("Server will continue without Elasticsearch connection.")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down gracefully...")
    # Add any cleanup here (close connections, save state, etc.)
    try:
        # Clear session data
        session_manager.clear_all_sessions()
        logger.info("✓ Cleanup completed")
    except Exception as e:
        logger.error(f"Error during shutdown cleanup: {e}")


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
        description="The .txt file to upload. Recommended max size: 200MB"
    ),
    split_mode: str = Query(
        default="auto",
        description="How to split text: 'auto' (detect), 'line' (per-line for Bible/verses), 'nltk' (paragraphs)",
        enum=["auto", "line", "nltk"]
    )
):
    """
    Upload .txt file with streaming read for RAM optimization.
    
    **split_mode options:**
    - `auto`: Auto-detect based on file structure
    - `line`: Split by newlines (for Bible, verse-per-line files) 
    - `nltk`: Use NLTK sentence tokenizer (for paragraph-style text)
    
    **Supported encodings:** UTF-8, UTF-16, Latin-1, CP1252 (Windows)
    """
    # Allow any text file extension
    allowed_extensions = [".txt", ".text", ".md", ".csv", ".log", ".dat"]
    file_ext = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""
    
    if file_ext and file_ext not in allowed_extensions:
        # Just warn, don't block - try to process anyway
        print(f"[Upload] Warning: Unusual file extension '{file_ext}', will try to process as text")

    # Streaming read to prevent RAM overflow with large files
    chunks = []
    total_size = 0
    MAX_SIZE = 200 * 1024 * 1024  # 200MB limit
    
    try:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            chunks.append(chunk)
            total_size += len(chunk)
            
            if total_size > MAX_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"File too large. Maximum size is 200MB. Your file: {total_size / (1024*1024):.1f}MB"
                )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error reading file: {str(e)}"
        )
    
    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="File is empty or could not be read."
        )
    
    content_bytes = b"".join(chunks)
    
    # Try multiple encodings - cp1252 first for Windows files with smart quotes
    text = None
    best_encoding = None
    
    # First try strict UTF-8
    try:
        text = content_bytes.decode("utf-8")
        # Validate: check if result has mostly printable chars
        printable_ratio = sum(1 for c in text[:1000] if c.isprintable() or c in '\n\r\t') / min(len(text), 1000)
        if printable_ratio > 0.95:
            best_encoding = "utf-8"
            print(f"[Upload] Successfully decoded with UTF-8 (printable ratio: {printable_ratio:.2%})")
        else:
            text = None  # Reset, try other encodings
    except UnicodeDecodeError:
        pass
    
    # If UTF-8 failed or gave bad results, try Windows encodings
    if text is None:
        for encoding in ["cp1252", "utf-8-sig", "utf-16", "iso-8859-1", "latin-1"]:
            try:
                candidate = content_bytes.decode(encoding)
                # Validate result
                printable_ratio = sum(1 for c in candidate[:1000] if c.isprintable() or c in '\n\r\t') / min(len(candidate), 1000)
                if printable_ratio > 0.90:
                    text = candidate
                    best_encoding = encoding
                    print(f"[Upload] Successfully decoded with {encoding} (printable ratio: {printable_ratio:.2%})")
                    break
            except (UnicodeDecodeError, LookupError):
                continue
    
    if text is None:
        # Last resort: decode with errors='replace' to replace bad chars with ?
        text = content_bytes.decode("utf-8", errors="replace")
        print(f"[Upload] Warning: Used fallback decoding with character replacement")
    
    # Clean up text: remove null bytes, normalize line endings
    text = text.replace("\x00", "")  # Remove null bytes
    text = text.replace("\r\n", "\n").replace("\r", "\n")  # Normalize line endings
    
    # Remove BOM if present
    if text.startswith("\ufeff"):
        text = text[1:]
    
    try:
        sentences = split_into_sentences(text, split_mode=split_mode)
        print(f"[Upload] Split mode: {split_mode}, Total sentences: {len(sentences)}")
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error splitting text into sentences: {str(e)}"
        )
    
    if not sentences:
        raise HTTPException(
            status_code=400, 
            detail="No valid sentences found in file. Make sure the file contains readable text."
        )

    # Index sentences with batch processing
    try:
        file_id = str(uuid.uuid4())
        max_level = index_sentences_batch(sentences, file_id=file_id, batch_size=500)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error indexing sentences: {str(e)}"
        )

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
    Receive user question and execute full flow with MULTI-LEVEL retrieval.
    
    Level 0: Keyword combinations (most specific → least specific)
    Level 1: Single keyword search
    Level 2: Synonym-based search
    Level 3: Keyword + Magical words combinations
    """
    logger.info(f"[API /ask] New request - query='{req.query}', limit={req.limit}")
    
    # Check if data exists
    if get_document_count() == 0:
        raise HTTPException(
            status_code=404, 
            detail="No documents found. Please upload a file first using POST /upload"
        )
    
    # Step 1: Extract clean keywords (filtered from magic words)
    clean_keywords = extract_clean_keywords(req.query)
    
    logger.info(f"[API /ask] Extracted keywords: {clean_keywords}")
    print(f"[DEBUG] Query: '{req.query}' → Keywords extracted: {clean_keywords}")
    
    if not clean_keywords:
        # Fallback: use simple word extraction
        clean_keywords = [w for w in req.query.lower().split() if len(w) > 3][:5]
        print(f"[DEBUG] Fallback keywords: {clean_keywords}")

    # Pre-Level 0: Biblical parallels analysis + supporting pulls
    biblical_parallels = analyze_biblical_parallels(req.query)
    # Store in initial state for Level 0.0 pagination
    initial_state = {
        "current_level": 0,
        "level_offsets": {"0.0": 0, "0": 0, "1": 0, "2": 0, "3": 0, "4": 0},
        "used_sentence_ids": [],
        "biblical_parallels": biblical_parallels
    }
    
    biblical_parallels_sentences, biblical_used_texts = gather_biblical_parallels_sentences(
        biblical_parallels,
        existing_texts=set(),
        base_query=req.query,
    )
    logger.info(
        f"[API /ask] Biblical parallels extracted: stories={len(biblical_parallels.get('stories_characters', []))}, "
        f"refs={len(biblical_parallels.get('scripture_references', []))}, "
        f"metaphors={len(biblical_parallels.get('biblical_metaphors', []))}, "
        f"keywords={len(biblical_parallels.get('keywords', []))}; sentences={len(biblical_parallels_sentences)}"
    )
    
    # Prepare Level 2/3 synonym debug info for display
    level2_synonyms = []
    level3_synonym_magic_pairs = []
    level2_synonyms_by_keyword = []
    level3_synonym_magic_by_keyword = []
    try:
        display_retriever = MultiLevelRetriever(clean_keywords)
        level2_synonyms = display_retriever._get_all_synonym_terms()[:30]
        magic_words_preview = get_magical_words_for_level3()[:5]
        synonym_preview = level2_synonyms[:5]
        level3_synonym_magic_pairs = [
            f"{syn} + {magic}" for syn in synonym_preview for magic in magic_words_preview
        ][:50]

        # Group synonyms by keyword for clarity
        for kw in clean_keywords:
            syns = generate_synonyms(kw)[:10]
            level2_synonyms_by_keyword.append({"keyword": kw, "synonyms": syns})
            # Build Level 3 pairs per keyword (using first few synonyms and magic words)
            syn_preview_kw = syns[:5]
            pairs_kw = [f"{s} + {m}" for s in syn_preview_kw for m in magic_words_preview][:20]
            level3_synonym_magic_by_keyword.append({"keyword": kw, "pairs": pairs_kw})
    except Exception as e:
        logger.warning(f"[API /ask] Unable to build synonym preview: {e}")

    # Step 2: Get first batch of sentences using multi-level retrieval
    # Count meaningful words in original query (excluding stopwords and question words)
    stopwords = {'what', 'where', 'when', 'who', 'why', 'how', 'which', 'whom', 'whose',
                 'is', 'are', 'was', 'were', 'be', 'been', 'being',
                 'the', 'a', 'an', 'and', 'or', 'but', 'if', 'so', 'as',
                 'to', 'of', 'in', 'on', 'at', 'by', 'for', 'with', 'about',
                 'do', 'does', 'did', 'can', 'could', 'will', 'would', 'should', 'may', 'might',
                 'this', 'that', 'these', 'those', 'it', 'its'}
    
    # Extract meaningful nouns from query
    query_words = [w.lower().strip('?!.,;:') for w in req.query.split()]
    meaningful_query_words = [w for w in query_words if w not in stopwords and len(w) > 2]
    
    print(f"[DEBUG] Meaningful words in query: {meaningful_query_words}")
    
    # If query has only 1 meaningful word → start from Level 1 (keyword + magical words)
    # NEW LOGIC: Level 1 = keyword + magic words (e.g., "heaven is")
    if len(meaningful_query_words) <= 1:
        # Single keyword query → start at Level 1 for contextual search
        initial_state = {
            "current_level": 1,  # Changed from 3 to 1
            "level_offsets": {"0.0": 0, "0": 0, "1": 0, "2": 0, "3": 0, "4": 0},
            "used_sentence_ids": [],  # Start fresh - Level 0+ should not be filtered by Level 0.0
            "biblical_parallels": biblical_parallels
        }
        print(f"[INFO] Only 1 meaningful word found → Starting from Level 1 (keyword + magic words)")
    else:
        initial_state = {
            "current_level": 0,
            "level_offsets": {"0.0": 0, "0": 0, "1": 0, "2": 0, "3": 0, "4": 0},
            "used_sentence_ids": [],  # Start fresh - Level 0+ should not be filtered by Level 0.0
            "biblical_parallels": biblical_parallels
        }
    
    source_sentences, updated_state, level_used = get_next_batch(
        session_state=initial_state,
        keywords=clean_keywords,
        batch_size=req.limit if req.limit else 15,
        enabled_levels=req.enabled_levels if req.enabled_levels else None,
        original_query=req.query,  # NEW: Pass original query for semantic search
        semantic_count=5  # NEW: Always get 5 semantic results
    )
    
    if not source_sentences:
        # Fallback to old method if multi-level returns nothing
        logger.warning(f"[API /ask] Multi-level retrieval returned no results, using fallback")
        source_sentences = get_top_unique_sentences_grouped(
            req.query, 
            limit=req.limit,
            buffer_percentage=req.buffer_percentage
        )

    # NOTE: Do NOT merge biblical_parallels_sentences into source_sentences
    # They are displayed separately in UI:
    # - Level 0.0 (Biblical Parallels) section shows biblical_sources
    # - Source Sentences section shows only Level 0+ sentences (source_sentences)
    
    # Dedup source_sentences to remove any overlap with Level 0.0
    # This ensures the same sentence doesn't appear in both sections
    source_sentences, _ = deduplicate_sentences(
        source_sentences,
        existing_texts=biblical_used_texts,  # Remove sentences already in Level 0.0
        similarity_threshold=0.95,
    )
    
    logger.info(f"[API /ask] Retrieved {len(source_sentences)} source sentences (Level 0+), {len(biblical_parallels_sentences)} biblical sources (Level 0.0)")
    
    if not source_sentences:
        raise HTTPException(
            status_code=404, 
            detail="No source sentences found matching your query. Try rephrasing your question."
        )

    # Step 3: Generate question variants + extract keyword meaning
    question_variants = generate_question_variants(req.query)
    
    # Use pre-provided keyword_meaning if available, otherwise generate via LLM
    if req.keyword_meaning:
        keyword_meaning = req.keyword_meaning
        print(f"[INFO] Using pre-provided keyword_meaning")
    else:
        keyword_meaning = extract_keywords(req.query)
        print(f"[INFO] Generated keyword_meaning via LLM")

    # Step 4: Build final prompt with custom_prompt support
    prompt = build_final_prompt(
        user_query=req.query,
        question_variants=question_variants,
        keyword_meaning=keyword_meaning,
        source_sentences=source_sentences,
        continue_mode=False,
        custom_prompt=req.custom_prompt,
        biblical_parallels=biblical_parallels,
        biblical_sources=biblical_parallels_sentences,
    )

    # Step 5: Call LLM
    answer = call_llm(prompt)
    
    # Step 6: Create session with keywords and level tracking
    session = session_manager.create_session(
        query=req.query, 
        max_level=20,  # 21 levels: 0-20 for deep testing
        keywords=clean_keywords
    )
    
    # IMPORTANT: Update session.used_sentences first from state_dict
    # This ensures all sentences from get_next_batch are tracked
    all_used_texts = set(updated_state.get("used_sentence_ids", []))
    all_used_texts.update([s["text"] for s in source_sentences])
    
    # Add biblical_parallels to updated_state for session storage
    updated_state["biblical_parallels"] = biblical_parallels
    
    # Update session with complete state from retriever
    session_manager.update_session(
        session.session_id,
        used_sentences=list(all_used_texts),  # Pass ALL used texts
        question_variants=question_variants,
        keywords=keyword_meaning,
        state_dict=updated_state
    )
    
    # Calculate current_level from state
    current_level = updated_state.get("current_level", 0)
    
    # can_continue = True if current_level < 20 (still have levels to explore)
    can_continue = current_level <= 20

    return AskResponse(
        session_id=session.session_id,
        answer=answer,
        question_variants=question_variants,
        keywords=clean_keywords,  # Add extracted keywords list
        level2_synonyms=level2_synonyms,
        level2_synonyms_by_keyword=level2_synonyms_by_keyword,
        level3_synonym_magic_pairs=level3_synonym_magic_pairs,
        level3_synonym_magic_by_keyword=level3_synonym_magic_by_keyword,
        keyword_meaning=keyword_meaning,
        source_sentences=source_sentences,
        current_level=level_used,
        max_level=20,
        prompt_used=prompt,
        can_continue=can_continue,
        sentences_retrieved=len(source_sentences),
        buffer_applied=req.buffer_percentage if req.buffer_percentage else 0,
        biblical_parallels=biblical_parallels,
        biblical_sources=biblical_parallels_sentences
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
    "Tell me more" - Progressive exploration using multi-level retrieval.
    
    Automatically moves through levels:
    Level 0 → Level 1 → Level 2 → Level 3
    
    Each call fetches next batch of sentences, avoiding previously used ones.
    """
    logger.info(f"[API /continue] Session={req.session_id}, limit={req.limit}")
    
    # Get session
    session = session_manager.get_session(req.session_id)
    if not session:
        logger.warning(f"[API /continue] Session not found: {req.session_id}")
        raise HTTPException(
            status_code=404,
            detail="Session not found or expired (30 min timeout). Please ask a new question with POST /ask"
        )
    
    # Check if can continue (unlimited now, relies on content availability)
    # The get_next_batch function will return empty references if no more data is found
    # and we can handle that via the return check below.
    # if session.current_level > 3:
    #    pass 

    
    # Get session state for retriever
    session_state = session.get_state_dict()
    
    # Use stored keywords from session
    keywords = session.keywords if session.keywords else [w for w in session.original_query.lower().split() if len(w) > 3][:5]

    # Prepare Level 2/3 synonym debug info for display
    level2_synonyms = []
    level3_synonym_magic_pairs = []
    level2_synonyms_by_keyword = []
    level3_synonym_magic_by_keyword = []
    try:
        display_retriever = MultiLevelRetriever(keywords)
        level2_synonyms = display_retriever._get_all_synonym_terms()[:30]
        magic_words_preview = get_magical_words_for_level3()[:5]
        synonym_preview = level2_synonyms[:5]
        level3_synonym_magic_pairs = [
            f"{syn} + {magic}" for syn in synonym_preview for magic in magic_words_preview
        ][:50]

        for kw in keywords:
            syns = generate_synonyms(kw)[:10]
            level2_synonyms_by_keyword.append({"keyword": kw, "synonyms": syns})
            syn_preview_kw = syns[:5]
            pairs_kw = [f"{s} + {m}" for s in syn_preview_kw for m in magic_words_preview][:20]
            level3_synonym_magic_by_keyword.append({"keyword": kw, "pairs": pairs_kw})
    except Exception as e:
        logger.warning(f"[API /continue] Unable to build synonym preview: {e}")
    
    # Get next batch using multi-level retriever
    # DISABLE forced semantic results for "Tell Me More" to ensure clean level progression
    source_sentences, updated_state, level_used = get_next_batch(
        session_state=session_state,
        keywords=keywords,
        batch_size=req.limit if req.limit else 15,
        original_query=session.original_query,
        semantic_count=0  
    )
    
    # FALLBACK: If levels 0-3 yielded nothing (or we skipped past them), 
    # force a check on Level 4 (Vector) to ensure we don't return empty-handed prematurely.
    if not source_sentences:
        logger.info("[API /continue] No results from current level walk. Forcing Level 4 (Vector) fallback.")
        # Temporarily force current_level to 4 in a copy of the state
        fallback_state = session_state.copy()
        fallback_state["current_level"] = 4
        
        # Call get_next_batch strictly for Level 4
        # We use enabled_levels=[4] to be sure
        fallback_sentences, fallback_updated_state, fallback_level_used = get_next_batch(
            session_state=fallback_state,
            keywords=keywords,
            batch_size=req.limit if req.limit else 15,
            original_query=session.original_query,
            enabled_levels=[4],
            semantic_count=0
        )
        
        if fallback_sentences:
            source_sentences = fallback_sentences
            updated_state = fallback_updated_state
            level_used = fallback_level_used
            logger.info(f"[API /continue] Fallback successful! Found {len(source_sentences)} sentences.")
    
    # If no more sentences, return response with can_continue=False
    if not source_sentences:
        return ContinueResponse(
            session_id=session.session_id,
            answer="All available information has been explored. Please start a new conversation with a different question.",
            question_variants=[],
            keywords=session.keywords if hasattr(session, 'keywords') and session.keywords else [],
            level2_synonyms=level2_synonyms,
                level2_synonyms_by_keyword=level2_synonyms_by_keyword,
            level3_synonym_magic_pairs=level3_synonym_magic_pairs,
                level3_synonym_magic_by_keyword=level3_synonym_magic_by_keyword,
            keyword_meaning="All keywords have been fully explored.",
            source_sentences=[],
            current_level=updated_state.get("current_level", 21),
            max_level=20,
            prompt_used="",
            can_continue=False,
            sentences_retrieved=0,
            buffer_applied=0
        )
    
    # Generate NEW question variants (deeper exploration)
    question_variants = generate_question_variants(
        session.original_query,
        previous_variants=session.used_variants,
        continue_mode=True
    )
    
    # Generate deeper keyword meaning
    keyword_meaning = extract_keywords(
        session.original_query,
        previous_keywords=session.previous_keywords,
        continue_mode=True
    )
    
    # Build new prompt for deeper exploration
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
    
    # IMPORTANT: Sync all used sentences from state_dict
    # This ensures no duplicates in future /continue calls
    all_used_texts = set(updated_state.get("used_sentence_ids", []))
    all_used_texts.update([s["text"] for s in source_sentences])
    
    # Update session with new state
    session_manager.update_session(
        session.session_id,
        used_sentences=list(all_used_texts),  # Pass ALL used texts from state
        question_variants=question_variants,
        keywords=keyword_meaning,
        increment_level=True,
        state_dict=updated_state
    )
    
    # Get current level from updated state
    current_level = updated_state.get("current_level", level_used)
    
    # can_continue = True if there are still levels to explore
    can_continue = current_level <= 20
    
    return ContinueResponse(
        session_id=session.session_id,
        answer=answer,
        question_variants=question_variants,
        keywords=session.keywords if hasattr(session, 'keywords') and session.keywords else [],
        level2_synonyms=level2_synonyms,
        level2_synonyms_by_keyword=level2_synonyms_by_keyword,
        level3_synonym_magic_pairs=level3_synonym_magic_pairs,
        level3_synonym_magic_by_keyword=level3_synonym_magic_by_keyword,
        keyword_meaning=keyword_meaning,
        source_sentences=source_sentences,
        current_level=level_used,
        max_level=20,
        prompt_used=prompt,
        can_continue=can_continue,
        continue_count=session.continue_count + 1,
        sentences_retrieved=len(source_sentences),
        buffer_applied=req.buffer_percentage if req.buffer_percentage else 0
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


# ============================================================
# DEBUG ENDPOINTS (for testing)
# ============================================================

@app.get(
    "/debug/keywords",
    tags=["🔧 Debug"],
    summary="Debug: Extract and analyze keywords",
    description="Extract keywords from query and show filtering details"
)
async def debug_keywords(query: str):
    """Debug endpoint to see keyword extraction details."""
    from services.keyword_extractor import (
        extract_keywords_raw,
        filter_magic_words,
        extract_keywords,
        generate_keyword_combinations,
        generate_synonyms,
        generate_keyword_magical_pairs,
        MAGIC_WORDS
    )
    
    raw = extract_keywords_raw(query)
    filtered = filter_magic_words(raw)
    final = extract_keywords(query)
    combinations = generate_keyword_combinations(final)
    
    # Get synonyms for each keyword
    synonyms = {}
    for kw in final[:3]:  # Limit to avoid too many API calls
        synonyms[kw] = generate_synonyms(kw)
    
    # Get magical pairs
    magical_pairs = generate_keyword_magical_pairs(final[:2])[:10]  # Limit
    
    return {
        "query": query,
        "raw_keywords": raw,
        "filtered_keywords": filtered,
        "final_keywords": final,
        "magic_words_count": len(MAGIC_WORDS),
        "combinations": [list(c) for c in combinations[:10]],
        "synonyms": synonyms,
        "magical_pairs": [list(p) for p in magical_pairs],
    }


@app.get(
    "/debug/level/{level}",
    tags=["🔧 Debug"],
    summary="Debug: Test specific level retrieval",
    description="Fetch sentences from a specific level only"
)
async def debug_level(
    level: int,
    query: str,
    limit: int = 10
):
    """Debug endpoint to test each level independently."""
    from services.keyword_extractor import extract_keywords
    from services.multi_level_retriever import MultiLevelRetriever
    
    keywords = extract_keywords(query)
    if not keywords:
        keywords = [w for w in query.lower().split() if len(w) > 3][:5]
    
    retriever = MultiLevelRetriever(keywords)
    used_texts = set()
    
    if level == 0:
        sentences, offset, exhausted = retriever.fetch_level0_sentences(
            offset=0, limit=limit, used_texts=used_texts
        )
        return {
            "level": 0,
            "strategy": "keyword_combinations",
            "keywords": keywords,
            "sentences": sentences,
            "offset": offset,
            "exhausted": exhausted
        }
    
    elif level == 1:
        sentences, offset, exhausted = retriever.fetch_level1_sentences(
            offset=0, limit=limit, used_texts=used_texts
        )
        return {
            "level": 1,
            "strategy": "single_keywords",
            "keywords": keywords,
            "sentences": sentences,
            "offset": offset,
            "exhausted": exhausted
        }
    
    elif level == 2:
        sentences, k_off, s_off, exhausted = retriever.fetch_level2_sentences(
            keyword_offset=0, synonym_offset=0, limit=limit, used_texts=used_texts
        )
        return {
            "level": 2,
            "strategy": "synonyms",
            "keywords": keywords,
            "sentences": sentences,
            "keyword_offset": k_off,
            "synonym_offset": s_off,
            "exhausted": exhausted
        }
    
    elif level == 3:
        sentences, offset, exhausted = retriever.fetch_level3_sentences(
            offset=0, limit=limit, used_texts=used_texts
        )
        return {
            "level": 3,
            "strategy": "keyword_magical_pairs",
            "keywords": keywords,
            "sentences": sentences,
            "offset": offset,
            "exhausted": exhausted
        }
    
    else:
        return {"error": f"Invalid level {level}. Valid: 0, 1, 2, 3"}


@app.get(
    "/debug/session/{session_id}",
    tags=["🔧 Debug"],
    summary="Debug: View session state",
    description="View current session state including level offsets and used sentences"
)
async def debug_session(session_id: str):
    """Debug endpoint to inspect session state."""
    session = session_manager.get_session(session_id)
    
    if not session:
        return {"error": "Session not found or expired"}
    
    return {
        "session_id": session.session_id,
        "original_query": session.original_query,
        "current_level": session.current_level,
        "max_level_available": session.max_level_available,
        "level_offsets": session.level_offsets,
        "keywords": session.keywords,
        "used_sentences_count": len(session.used_sentences),
        "used_variants_count": len(session.used_variants),
        "continue_count": session.continue_count,
        "created_at": session.created_at.isoformat(),
        "last_accessed": session.last_accessed.isoformat()
    }
