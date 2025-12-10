# streamlit_app.py
"""
Streamlit UI for AI Vector Search Demo
======================================
A user-friendly web interface to interact with the API.
"""
import streamlit as st
import requests
import json
import os
from typing import Optional, List

# Configuration
# Use environment variable for production, fallback to localhost for local dev
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Page configuration
st.set_page_config(
    page_title="AI Chat",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .stButton > button {
        width: 100%;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        margin: 1rem 0;
    }
    .error-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        margin: 1rem 0;
    }
    .info-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #cce5ff;
        border: 1px solid #b8daff;
        margin: 1rem 0;
    }
    .source-sentence {
        padding: 0.5rem;
        margin: 0.25rem 0;
        background-color: #f8f9fa;
        border-left: 3px solid #007bff;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)


def check_api_health():
    """Check if API is running and healthy"""
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None


def upload_file(file, split_mode: str = "auto"):
    """Upload a file to the API (no timeout for large files)"""
    try:
        files = {"file": (file.name, file.getvalue(), "text/plain")}
        # Calculate expected time based on file size (rough estimate)
        file_size_mb = len(file.getvalue()) / (1024 * 1024)
        estimated_minutes = max(1, int(file_size_mb / 2))  # ~2MB/minute
        
        # Show progress message
        if file_size_mb > 10:
            print(f"[Upload] Large file detected ({file_size_mb:.1f}MB). Estimated time: {estimated_minutes} minutes")
        
        # No timeout for large files
        response = requests.post(
            f"{API_BASE_URL}/upload?split_mode={split_mode}", 
            files=files,
            timeout=None  # No timeout
        )
        return response.json(), response.status_code
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if "ConnectionError" in error_msg or "Connection refused" in error_msg:
            return {"detail": "Cannot connect to API. The server may have crashed. Please restart the server."}, 503
        elif "ReadTimeout" in error_msg:
            return {"detail": "Upload timed out. File may be too large or server is overloaded."}, 504
        else:
            return {"detail": f"Upload error: {error_msg[:200]}"}, 500
    except Exception as e:
        return {"detail": f"Unexpected error: {str(e)[:200]}"}, 500


def ask_question(query: str, custom_prompt: Optional[str] = None, 
                 limit: int = 15, buffer_percentage: int = 15, enabled_levels: Optional[List[int]] = None):
    """Send a question to the API"""
    try:
        payload = {
            "query": query,
            "limit": limit,
            "buffer_percentage": buffer_percentage
        }
        if custom_prompt:
            payload["custom_prompt"] = custom_prompt
        if enabled_levels is not None:
            payload["enabled_levels"] = enabled_levels
        
        # Use longer timeout for queries with custom prompts
        timeout_seconds = 600 if not custom_prompt or len(custom_prompt) < 1000 else 900
        
        response = requests.post(f"{API_BASE_URL}/ask", json=payload, timeout=timeout_seconds)
        if response.status_code == 200:
            return response.json(), response.status_code
        else:
            error_detail = f"API Error: {response.status_code}"
            try:
                error_json = response.json()
                error_detail = error_json.get('detail', error_detail)
            except:
                error_detail += f" - {response.text[:200]}"
            return {"detail": error_detail}, response.status_code
    except requests.exceptions.Timeout:
        return {
            "detail": "Request timed out. The query is taking too long. Try: 1) Shorter custom prompt, 2) Disable some levels, or 3) Wait and try again."
        }, 408
    except requests.exceptions.ConnectionError:
        return {
            "detail": "Cannot connect to API. The server may have crashed or is not running. Please check logs and restart if needed."
        }, 503
    except Exception as e:
        error_msg = str(e)
        return {"detail": f"Unexpected error: {error_msg[:200]}"}, 500


def continue_conversation(session_id: str, custom_prompt: Optional[str] = None,
                         limit: int = 15, buffer_percentage: int = 15):
    """Continue the conversation (Tell me more)"""
    try:
        payload = {
            "session_id": session_id,
            "limit": limit,
            "buffer_percentage": buffer_percentage
        }
        if custom_prompt:
            payload["custom_prompt"] = custom_prompt
        
        timeout_seconds = 600 if not custom_prompt or len(custom_prompt) < 1000 else 900
        
        response = requests.post(f"{API_BASE_URL}/continue", json=payload, timeout=timeout_seconds)
        if response.status_code == 200:
            return response.json(), response.status_code
        else:
            error_detail = f"API Error: {response.status_code}"
            try:
                error_json = response.json()
                error_detail = error_json.get('detail', error_detail)
            except:
                error_detail += f" - {response.text[:200]}"
            return {"detail": error_detail}, response.status_code
    except requests.exceptions.Timeout:
        return {
            "detail": "Request timed out. Try with a shorter custom prompt or wait and try again."
        }, 408
    except requests.exceptions.ConnectionError:
        return {
            "detail": "Cannot connect to API. The server may have crashed. Please check logs and restart if needed."
        }, 503
    except Exception as e:
        return {"detail": f"Unexpected error: {str(e)[:200]}"}, 500


def get_document_stats():
    """Get document statistics"""
    try:
        response = requests.get(f"{API_BASE_URL}/documents/count")
        return response.json(), response.status_code
    except Exception as e:
        return {"detail": str(e)}, 500


def delete_all_documents():
    """Delete all documents"""
    try:
        response = requests.delete(f"{API_BASE_URL}/documents")
        return response.json(), response.status_code
    except Exception as e:
        return {"detail": str(e)}, 500


# Initialize session state
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = []
if "can_continue" not in st.session_state:
    st.session_state.can_continue = False
if "selected_levels" not in st.session_state:
    st.session_state.selected_levels = None
if "continue_count" not in st.session_state:
    st.session_state.continue_count = 0


def generate_document_content(history: list, include_prompt: bool = True) -> str:
    """Generate document content from conversation history."""
    content = []
    content.append("=" * 60)
    content.append("AI CHAT - CONVERSATION DOCUMENT")
    content.append("=" * 60)
    content.append("")
    
    answer_num = 0
    last_prompt = ""
    
    for entry in history:
        result = entry.get("result", {})
        
        if entry["type"] == "ask":
            answer_num += 1
            content.append(f"QUESTION: {entry.get('question', 'N/A')}")
            content.append("-" * 40)
            content.append(f"ANSWER {answer_num}:")
            content.append(result.get("answer", "No answer available"))
            content.append("")
            last_prompt = result.get("prompt_used", "")
        else:  # continue
            answer_num += 1
            content.append("-" * 40)
            content.append(f"ANSWER {answer_num} (Tell me more):")
            content.append(result.get("answer", "No answer available"))
            content.append("")
            last_prompt = result.get("prompt_used", "")
    
    if include_prompt and last_prompt:
        content.append("=" * 60)
        content.append("PROMPT USED:")
        content.append("=" * 60)
        content.append(last_prompt)
    
    return "\n".join(content)


# Sidebar
with st.sidebar:
    st.title("AI Chat")
    st.markdown("---")
    
    # Health check
    health = check_api_health()
    if health:
        status_color = "🟢" if health.get("status") == "healthy" else "🟡" if health.get("status") == "degraded" else "🔴"
        st.markdown(f"{status_color} **API Status:** {health.get('status', 'unknown')}")
        st.markdown(f"📄 **Documents:** {health.get('documents_indexed', 0)}")
        st.markdown(f"💬 **Active Sessions:** {health.get('active_sessions', 0)}")
    else:
        st.error("❌ API not available. Make sure the server is running on port 8000.")
    
    st.markdown("---")
    
    # File Upload Section
    st.subheader("📁 Upload Document")
    uploaded_file = st.file_uploader(
        "Choose a text file",
        type=["txt", "text", "md", "csv", "log"],
        help="Upload a text file to index. Supported: .txt, .text, .md, .csv, .log. Maximum 200MB."
    )
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📤 Upload", disabled=uploaded_file is None):
            with st.spinner("Uploading and processing..."):
                result, status_code = upload_file(uploaded_file)
                if status_code == 200:
                    st.success(f"✅ Uploaded! {result.get('total_sentences', 0)} sentences indexed.")
                    st.session_state.conversation_history = []
                    st.session_state.session_id = None
                else:
                    st.error(f"❌ Error: {result.get('detail', 'Unknown error')}")
    
    with col2:
        if st.button("🗑️ Delete All"):
            with st.spinner("Deleting..."):
                result, status_code = delete_all_documents()
                if status_code == 200:
                    st.success("✅ All documents deleted")
                    st.session_state.conversation_history = []
                    st.session_state.session_id = None
                else:
                    st.error(f"❌ Error: {result.get('detail', 'Unknown error')}")
    
    st.markdown("---")
    
    # Settings (TEMPORARILY HIDDEN per client request)
    # st.subheader("⚙️ Settings")
    # limit = st.slider("Source sentences limit", min_value=5, max_value=50, value=15)
    # buffer_percentage = st.slider("Buffer percentage", min_value=10, max_value=20, value=15)
    
    # Use default values when Settings are hidden
    limit = 15
    buffer_percentage = 15
    
    # Level Selection
    st.markdown("### 🎯 Level Selection (for testing)")
    st.markdown("""
    <div style='font-size: 0.9em; line-height: 1.5; margin-bottom: 10px;'>
    Select which levels to search.<br/>
    Uncheck levels to skip them for<br/>
    faster testing.
    </div>
    """, unsafe_allow_html=True)
    
    # Use vertical layout for better text display
    level_0_enabled = st.checkbox("✓ Level 0", value=True, help="Keyword combinations (all keywords together)", key="lvl0")
    level_1_enabled = st.checkbox("✓ Level 1", value=True, help="Single keywords", key="lvl1")
    level_2_enabled = st.checkbox("✓ Level 2", value=True, help="Synonyms", key="lvl2")
    level_3_enabled = st.checkbox("✓ Level 3", value=True, help="Keyword + Magic words (e.g., 'heaven is')", key="lvl3")
    
    # Store selected levels
    enabled_levels = []
    if level_0_enabled:
        enabled_levels.append(0)
    if level_1_enabled:
        enabled_levels.append(1)
    if level_2_enabled:
        enabled_levels.append(2)
    if level_3_enabled:
        enabled_levels.append(3)
    
    if not enabled_levels:
        st.warning("⚠️ Select at least one level")
    else:
        levels_text = ', '.join([f'Level {l}' for l in enabled_levels])
        st.markdown(f"""
        <div style='background-color: #cce5ff; padding: 8px; border-radius: 5px; 
                    font-size: 0.85em; line-height: 1.4; border-left: 3px solid #007bff;'>
        ✓ Searching levels:<br/><strong>{levels_text}</strong>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("""
    ### 💡 How to use:
    1. Upload a `.txt` file
    2. Ask a question
    3. Click "Tell me more" to explore deeper
    4. Add custom prompts for specific formatting
    """)


# Main content
st.title("🤖 AI Chat")
st.markdown("Ask questions about your uploaded documents with multi-level retrieval.")

# Check if documents are available
stats, _ = get_document_stats()
if not stats.get("ready", False):
    st.warning("⚠️ No documents uploaded. Please upload a .txt file using the sidebar.")
else:
    st.info(f"📄 **{stats.get('total_documents', 0)}** sentences indexed across **{stats.get('levels_available', 0)}** levels")

st.markdown("---")

# Question input
col1, col2 = st.columns([3, 1])
with col1:
    user_question = st.text_area(
        "Ask a question:",
        placeholder="Type your question here...",
        height=100,
        key="question_input"
    )

with col2:
    default_prompt = """You are a sermon-writing assistant. You will receive four inputs:

{question} – the spiritual request or theme.

{meaning} – the distilled meaning of the question.

PRIMARY SOURCES – semantically relevant sentences retrieved using vector similarity.

SECONDARY SOURCES – additional keyword-matched sentences that may support context.

Your job is to generate a sermon using ONLY the source material that is directly relevant to the user's question.
You must STRICTLY filter the provided sources and USE ONLY the sentences that relate clearly to the question and its meaning.

The user may ask the same question repeatedly, or ask a similar question, or continue with a follow-up thought.
Treat every repeated or follow-up question as "tell me more."
Always generate a deeper, richer, fresh sermon with a new title and a new introduction, using unused relevant source sentences when possible.

Do not invent, add, or borrow content outside the selected relevant source sentences.
You may also incorporate contextual material from EGW, but ONLY when it is clearly relevant to the question and meaning.
Never reveal, mention, cite, or hint that EGW or any book was used.
The sermon must contain no source names, no authors, and no references.

GREETING RULE

Begin with a warm greeting.

If {name_type} is provided, use it naturally:
"Hello, {name_type}, let's explore this together."
"Welcome, {name_type}. I'm glad to walk through this with you."
"Hi {name_type}, I'm excited to share this message with you."

If {name_type} is not provided, use neutral versions:
"Hello! Let's explore this together."
"Welcome! I'm glad to walk through this message with you."

TITLE & INTRODUCTION RULE (MANDATORY)

Always generate a fresh main sermon title. It must be unique, meaningful, and source-based.

Always generate a fresh introduction paragraph(s) immediately after the title. Do not create a separate "Introduction Title."

For repeated or follow-up questions, produce a new title and new introduction, reflecting deeper insight and unused relevant source sentences.

SOURCE USAGE RULES

Filter both PRIMARY and SECONDARY SOURCES. Select only sentences that directly relate to the {question} and {meaning}.

You may use EGW content, but ONLY if it aligns with the question and meaning, without ever mentioning EGW.

Ignore any irrelevant sentences completely.

Do not create new theology, stories, metaphors, or ideas outside the filtered sources.

Rearrange, rephrase, and interconnect the filtered sources into a flowing narrative sermon.

Transform sources into a fresh sermon — do not copy verbatim.

Section titles and narrative flow must be derived from the meaning + filtered sources.

SERMON STRUCTURE (NON-NEGOTIABLE, SIMPLIFIED)

Title
[Fresh, source-based sermon title — unique every time]

Introduction
[Introduction paragraph(s) — engaging, reflective, fresh every time]

Theme Section 1
[Section paragraphs]

Theme Section 2
[Section paragraphs]

Theme Section 3
[Section paragraphs]

Optional Theme Section 4 or 5
[Section paragraphs]

Closing / Reflection
[Closing paragraph(s) — summarize key themes, leave reader with reflection]

Minimum length: 1,200 words, unless otherwise specified.

NARRATIVE & STYLE RULES

Maintain a warm, personal, reflective tone.

Speak directly to the reader.

Titles must be meaningful and tightly connected to the content.

Identify 3–5 core themes from filtered sources.

Do not mention rhetorical devices.

Do not reuse past sermons; every sermon must be fresh.

Forbidden words: symphony, tapestry, dance.

Plain text only — no bullets, emojis, or markup.

MANDATORY RHETORICAL DEVICES (BLENDED NATURALLY)

Seamlessly blend the following:
Alliteration, Allusion, Anadiplosis, Analogy, Anaphora, Anecdote, Antanaclasis, Antithesis,
Assonance, Asyndeton, Chiasmus, Climax, Consonance, Diacope, Ellipsis, Epanalepsis,
Epanorthosis, Epistrophe, Euphemism, Hyperbole, Irony, Litotes, Metaphor, Metonymy,
Onomatopoeia, Oxymoron, Parallelism, Paradox, Personification, Pleonasm, Polysyndeton,
Rhetorical Question, Simile, Symploce, Synecdoche, Understatement, Zeugma.

Use them organically, never mechanically.

INPUT FORMAT

{
"name_type": "... or null",
"question": "...",
"meaning": "...",
"primary_sources": "...",
"secondary_sources": "..."
}

OUTPUT FORMAT

A fully written sermon in the exact structure described.
No explanations. No bullet points. No external content.
No mention or hint of EGW, book titles, authors, or sources.

ENDING INSTRUCTION

If you understand, proceed by generating the sermon using the question, meaning,
and ONLY the relevant filtered source sentences.
Always produce a deeper, fresh sermon for repeated or follow-up questions.
Never skip or reuse the main title or introduction."""
    
    custom_prompt = st.text_area(
        "Custom prompt (optional):",
        value=default_prompt,
        height=100,
        key="custom_prompt_input",
        help="You can edit this default sermon prompt or replace it with your own"
    )

# Action buttons
col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    ask_button = st.button("🔍 Ask Question", type="primary", use_container_width=True)
with col2:
    # Debug: show can_continue state
    can_continue_now = st.session_state.get("can_continue", False)
    # Calculate next continue_count for button label
    continue_count = 0
    if st.session_state.conversation_history:
        # Count how many "continue" entries exist in history
        continue_count = sum(1 for entry in st.session_state.conversation_history if entry.get("type") == "continue")
    next_count = continue_count + 1
    
    # Allow continuous "Tell me more" regardless of API suggestion, as long as session exists
    session_active = st.session_state.session_id is not None
    
    button_label = f"📚 Tell me more ({next_count})"
    continue_button = st.button(
        button_label, 
        disabled=not session_active,
        use_container_width=True,
        key="continue_btn"
    )
with col3:
    if st.button("🔄 New Conversation", use_container_width=True):
        st.session_state.conversation_history = []
        st.session_state.session_id = None
        st.session_state.can_continue = False
        st.rerun()

# Show current state for debugging
if st.session_state.session_id:
    st.caption(f"🔑 Session: {st.session_state.session_id[:20]}... | Can continue: {st.session_state.can_continue}")

# Handle Ask button
if ask_button and user_question:
    # Show warning for long custom prompts
    if custom_prompt and len(custom_prompt) > 500:
        st.info("⏳ Long custom prompt detected. This may take 30-60 seconds to process...")
    
    with st.spinner("🔍 Searching and generating answer... Please wait, this may take a while for long prompts."):
        try:
            result, status_code = ask_question(
                query=user_question,
                custom_prompt=custom_prompt if custom_prompt else None,
                limit=limit,
                buffer_percentage=buffer_percentage,
                enabled_levels=enabled_levels if enabled_levels else None
            )
            
            if status_code == 200 and "answer" in result:
                st.session_state.session_id = result.get("session_id")
                st.session_state.can_continue = result.get("can_continue", False)
                st.session_state.selected_levels = enabled_levels if enabled_levels else None
                st.session_state.conversation_history.append({
                    "type": "ask",
                    "question": user_question,
                    "result": result,
                    "enabled_levels": enabled_levels if enabled_levels else None
                })
                st.rerun()
            else:
                error_msg = result.get('detail', 'Unknown error occurred')
                st.error(f"❌ Error: {error_msg}")
                st.session_state.can_continue = False
        except Exception as e:
            st.error(f"❌ Unexpected error: {str(e)}")
            st.session_state.can_continue = False

# Handle Continue button
if continue_button and st.session_state.session_id:
    with st.spinner("📚 Exploring deeper levels..."):
        result, status_code = continue_conversation(
            session_id=st.session_state.session_id,
            custom_prompt=custom_prompt if custom_prompt else None,
            limit=limit,
            buffer_percentage=buffer_percentage
        )
        
        if status_code == 200:
            st.session_state.can_continue = result.get("can_continue", False)
            st.session_state.conversation_history.append({
                "type": "continue",
                "result": result
            })
            # Rerun to update button states
            st.rerun()
        else:
            st.error(f"❌ Error: {result.get('detail', 'Unknown error')}")
            st.session_state.can_continue = False
            st.rerun()

# Display conversation history
if st.session_state.conversation_history:
    st.markdown("---")
    st.subheader("💬 Conversation")
    
    for i, entry in enumerate(st.session_state.conversation_history):
        result = entry["result"]
        
        if entry["type"] == "ask":
            st.markdown(f"### 🙋 Question")
            st.markdown(f"> {entry['question']}")
            enabled_levels_entry = entry.get("enabled_levels", st.session_state.get("selected_levels"))
        else:
            # Display continue_count if available, otherwise show current_level
            tell_more_count = result.get('continue_count', result.get('current_level', '?'))
            st.markdown(f"### 📚 Tell me more ({tell_more_count})")
            enabled_levels_entry = st.session_state.get("selected_levels")
        
        # Answer
        st.markdown("### 🤖 Answer")
        st.markdown(result.get("answer", "No answer available"))
        
        # === ALWAYS VISIBLE: Details ===
        st.markdown("### 📊 Details")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Current Level", result.get("current_level", 0))
        with col2:
            st.metric("Max Level", result.get("max_level", 0))
        with col3:
            st.metric("Sentences Retrieved", result.get("sentences_retrieved", 0))
        
        st.markdown("**Question Variants:**")
        st.text(result.get("question_variants", "N/A"))
        
        # === Keywords Section ===
        st.markdown("### 🔑 Extracted Keywords")
        keywords = result.get("keywords", [])
        if keywords:
            # Display keywords as tags/badges
            keywords_html = " ".join([
                f'<span style="background-color: #e3f2fd; color: #1976d2; padding: 5px 12px; border-radius: 15px; margin: 3px; display: inline-block; font-weight: 500;">{kw}</span>'
                for kw in keywords
            ])
            st.markdown(keywords_html, unsafe_allow_html=True)
        else:
            st.warning("No keywords extracted")
        
        st.markdown("**Keyword Meaning:**")
        st.text(result.get("keyword_meaning", "N/A"))

        # === Synonym visibility grouped by level ===
        level2_syns = result.get("level2_synonyms", [])
        level2_by_kw = result.get("level2_synonyms_by_keyword", [])
        level3_pairs = result.get("level3_synonym_magic_pairs", [])
        level3_by_kw = result.get("level3_synonym_magic_by_keyword", [])

        # === Level 0.0: Biblical Parallels ===
        st.markdown("### 📖 Level 0.0 (Biblical Parallels)")
        biblical_parallels = result.get("biblical_parallels", {})
        biblical_sources = result.get("biblical_sources", [])
        
        # Check if any parallels were actually extracted (not just empty arrays)
        stories = biblical_parallels.get("stories_characters", []) if biblical_parallels else []
        refs = biblical_parallels.get("scripture_references", []) if biblical_parallels else []
        metaphors = biblical_parallels.get("biblical_metaphors", []) if biblical_parallels else []
        bp_keywords = biblical_parallels.get("keywords", []) if biblical_parallels else []
        has_parallels = bool(stories or refs or metaphors or bp_keywords)
        
        if has_parallels:
            # Bible Stories / Characters
            if stories:
                st.markdown("**📜 Bible Stories / Characters (search terms):**")
                stories_html = " ".join([
                    f'<span style="background-color: #fce4ec; color: #c2185b; padding: 5px 12px; border-radius: 15px; margin: 3px; display: inline-block; font-weight: 500;">📜 {story}</span>'
                    for story in stories
                ])
                st.markdown(stories_html, unsafe_allow_html=True)
            
            # Scripture References
            if refs:
                st.markdown("**📖 Scripture References (search terms):**")
                refs_html = " ".join([
                    f'<span style="background-color: #e8f5e9; color: #2e7d32; padding: 5px 12px; border-radius: 15px; margin: 3px; display: inline-block; font-weight: 500;">📖 {ref}</span>'
                    for ref in refs
                ])
                st.markdown(refs_html, unsafe_allow_html=True)
            
            # Biblical Metaphors
            if metaphors:
                st.markdown("**🔮 Biblical Metaphors (search terms):**")
                metaphors_html = " ".join([
                    f'<span style="background-color: #fff3e0; color: #e65100; padding: 5px 12px; border-radius: 15px; margin: 3px; display: inline-block; font-weight: 500;">🔮 {m}</span>'
                    for m in metaphors
                ])
                st.markdown(metaphors_html, unsafe_allow_html=True)
            
            # Keywords (from biblical analysis)
            if bp_keywords:
                st.markdown("**🔑 Biblical Keywords (search terms):**")
                bp_kw_html = " ".join([
                    f'<span style="background-color: #e3f2fd; color: #1565c0; padding: 5px 12px; border-radius: 15px; margin: 3px; display: inline-block; font-weight: 500;">🔑 {kw}</span>'
                    for kw in bp_keywords
                ])
                st.markdown(bp_kw_html, unsafe_allow_html=True)
        else:
            st.info("No biblical parallels extracted for this query")
        
        # === Level 0.0 Source Sentences ===
        if biblical_sources:
            st.markdown(f"**📚 Level 0.0 Source Sentences ({len(biblical_sources)} total):**")
            
            # Group by source_type
            sources_by_type = {}
            for src in biblical_sources:
                stype = src.get("source_type", "Unknown")
                if stype not in sources_by_type:
                    sources_by_type[stype] = []
                sources_by_type[stype].append(src)
            
            # Display grouped by type with collapsible sections
            for stype, sentences in sources_by_type.items():
                with st.expander(f"**{stype}** ({len(sentences)} sentences)", expanded=False):
                    for i, s in enumerate(sentences, 1):
                        score = s.get("score", 0)
                        text = s.get("text", "")
                        st.markdown(f"""
                        <div style="background-color: #f8f9fa; padding: 10px; margin: 5px 0; border-radius: 8px; border-left: 3px solid #6c757d;">
                            <small style="color: #888;">#{i} | Score: {score:.2f}</small><br>
                            <span style="font-size: 0.95em;">{text}</span>
                        </div>
                        """, unsafe_allow_html=True)
        else:
            st.caption("No Level 0.0 source sentences found")

        # Level 0: show keyword combinations (all keywords together, then smaller combos)
        st.markdown("### 🔁 Level 0 (keyword combination)")
        if keywords:
            # Generate combinations from full to smallest
            from itertools import combinations
            combos = []
            n = len(keywords)
            for size in range(n, 1, -1):  # From full length down to 2 keywords
                for combo in combinations(keywords, size):
                    combos.append(" ".join(combo))
            
            if combos:
                combo_html = " ".join([
                    f'<span style="background-color: #e3f2fd; color: #1976d2; padding: 5px 12px; border-radius: 15px; margin: 3px; display: inline-block; font-weight: 500;">{combo}</span>'
                    for combo in combos[:10]  # Show first 10 combinations
                ])
                st.markdown(combo_html, unsafe_allow_html=True)
                if len(combos) > 10:
                    st.caption(f"... and {len(combos) - 10} more combinations")
            else:
                st.info("No combinations available (need at least 2 keywords)")
        else:
            st.info("No keywords available")

        st.markdown("### 🔁 Level 1 (Single keywords)")
        if keywords:
            kw_html = " ".join([
                f'<span style="background-color: #e3f2fd; color: #1976d2; padding: 5px 12px; border-radius: 15px; margin: 3px; display: inline-block; font-weight: 500;">{kw}</span>'
                for kw in keywords
            ])
            st.markdown(kw_html, unsafe_allow_html=True)
        else:
            st.info("No keywords available")

        st.markdown("### 🔁 Level 2 Synonyms")
        if level2_by_kw:
            for item in level2_by_kw:
                kw = item.get("keyword", "")
                syns = item.get("synonyms", [])
                if not syns:
                    continue
                syn_html = " ".join([
                    f'<span style="background-color: #fff3cd; color: #856404; padding: 5px 12px; border-radius: 15px; margin: 3px; display: inline-block; font-weight: 500;">{syn}</span>'
                    for syn in syns
                ])
                st.markdown(f"**{kw}**: " + syn_html, unsafe_allow_html=True)
        elif level2_syns:
            syn_html = " ".join([
                f'<span style="background-color: #fff3cd; color: #856404; padding: 5px 12px; border-radius: 15px; margin: 3px; display: inline-block; font-weight: 500;">{syn}</span>'
                for syn in level2_syns
            ])
            st.markdown(syn_html, unsafe_allow_html=True)
        else:
            st.info("No Level 2 synonyms available")

        st.markdown("### ✨ Level 3 Synonym + Magic")
        if level3_by_kw:
            for item in level3_by_kw:
                kw = item.get("keyword", "")
                pairs = item.get("pairs", [])
                if not pairs:
                    continue
                pair_html = " ".join([
                    f'<span style="background-color: #e8f5e9; color: #2e7d32; padding: 5px 12px; border-radius: 15px; margin: 3px; display: inline-block; font-weight: 500;">{pair}</span>'
                    for pair in pairs
                ])
                st.markdown(f"**{kw}**: " + pair_html, unsafe_allow_html=True)
        elif level3_pairs:
            pair_html = " ".join([
                f'<span style="background-color: #e8f5e9; color: #2e7d32; padding: 5px 12px; border-radius: 15px; margin: 3px; display: inline-block; font-weight: 500;">{pair}</span>'
                for pair in level3_pairs
            ])
            st.markdown(pair_html, unsafe_allow_html=True)
        else:
            st.info("No Level 3 synonym+magic pairs available")
        
        # === ALWAYS VISIBLE: Source Sentences ===
        st.markdown("### 📄 Source Sentences")
        sources = result.get("source_sentences", [])
        # Filter out Level 0.0 sentences (they're shown separately above)
        sources = [s for s in sources if not (s.get("source_type") or "").startswith("Level 0.0")]
        if sources:
            for src in sources:
                level = src.get("level", 0)
                score = src.get("score", 0)
                text = src.get("text", "")
                is_primary = src.get("is_primary_source", False)
                source_type = src.get("source_type", "")
                
                # Use source_type if available, otherwise fall back to is_primary logic
                if source_type:
                    if source_type == "Vector":
                        border_color = "#28a745"  # Green for vector
                        label = f"🟢 {source_type}"
                    elif source_type.startswith("Level"):
                        border_color = "#17a2b8"  # Blue for level
                        label = f"🔵 {source_type}"
                    else:
                        border_color = "#6c757d"  # Gray for unknown
                        label = f"⚪ {source_type}"
                elif is_primary:
                    border_color = "#28a745"  # Green for vector
                    label = "🟢 Vector"
                else:
                    border_color = "#17a2b8"  # Blue for level
                    label = f"🔵 Level {level}"
                
                st.markdown(f"""
                <div class="source-sentence" style="border-left: 4px solid {border_color}; padding-left: 10px; margin-bottom: 10px;">
                    <strong>{label}</strong> (Score: {score:.2f})<br>
                    {text}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No source sentences available")
        
        # === ALWAYS VISIBLE: Full Prompt ===
        st.markdown("### 🔧 Full Prompt Sent to LLM")
        st.code(result.get("prompt_used", "N/A"), language="text")
        
        st.markdown("---")
    
    # Continue status
    if st.session_state.can_continue:
        st.info("💡 Click **Tell me more** to explore deeper levels")
    else:
        st.success("✅ All available information has been explored")

# Count continues for download buttons
# Count continues for download buttons
continue_count = sum(1 for entry in st.session_state.conversation_history if entry.get("type") == "continue")

# Download Document buttons based on continue count
if continue_count >= 5:
    st.markdown("---")
    st.markdown("### 📥 Download Options")
    
    col1, col2 = st.columns(2)
    
    # Generate document for current history (all responses)
    doc_content = generate_document_content(st.session_state.conversation_history, include_prompt=True)
    
    with col1:
        st.download_button(
            label="📄 Download Document",
            data=doc_content,
            file_name=f"conversation_{continue_count}_responses.txt",
            mime="text/plain",
            key="download_5_plus"
        )
    
    if continue_count >= 10:
        with col2:
            st.download_button(
                label="📑 Create Document",
                data=doc_content,
                file_name=f"full_conversation_{continue_count}_responses.txt",
                mime="text/plain",
                key="download_10_plus"
            )


# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9rem;">
    AI Chat | Powered by Elasticsearch + OpenAI | 
    <a href="http://localhost:8000/docs" target="_blank">API Docs</a>
</div>
""", unsafe_allow_html=True)
