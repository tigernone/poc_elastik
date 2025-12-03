# streamlit_app.py
"""
Streamlit UI for AI Vector Search Demo
======================================
A user-friendly web interface to interact with the API.
"""
import streamlit as st
import requests
import json
from typing import Optional

# Configuration
API_BASE_URL = "http://localhost:8000"

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
    """Upload a file to the API (timeout 30 minutes for large files)"""
    try:
        files = {"file": (file.name, file.getvalue(), "text/plain")}
        # Timeout 30 phút cho file lớn (31k+ sentences)
        response = requests.post(
            f"{API_BASE_URL}/upload?split_mode={split_mode}", 
            files=files,
            timeout=1800  # 30 minutes
        )
        return response.json(), response.status_code
    except requests.exceptions.Timeout:
        return {"detail": "Upload timed out after 30 minutes. File may be too large."}, 408
    except Exception as e:
        return {"detail": str(e)}, 500


def ask_question(query: str, custom_prompt: Optional[str] = None, 
                 limit: int = 15, buffer_percentage: int = 15):
    """Send a question to the API"""
    try:
        payload = {
            "query": query,
            "limit": limit,
            "buffer_percentage": buffer_percentage
        }
        if custom_prompt:
            payload["custom_prompt"] = custom_prompt
        
        response = requests.post(f"{API_BASE_URL}/ask", json=payload, timeout=600)
        if response.status_code == 200:
            return response.json(), response.status_code
        else:
            return {"detail": f"API Error: {response.status_code} - {response.text[:200]}"}, response.status_code
    except requests.exceptions.Timeout:
        return {"detail": "Request timed out. The response is taking too long. Please try with a shorter custom prompt."}, 408
    except requests.exceptions.ConnectionError:
        return {"detail": "Cannot connect to API. Make sure the server is running."}, 503
    except Exception as e:
        return {"detail": f"Error: {str(e)}"}, 500


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
        
        response = requests.post(f"{API_BASE_URL}/continue", json=payload, timeout=600)
        if response.status_code == 200:
            return response.json(), response.status_code
        else:
            return {"detail": f"API Error: {response.status_code} - {response.text[:200]}"}, response.status_code
    except requests.exceptions.Timeout:
        return {"detail": "Request timed out. The response is taking too long."}, 408
    except requests.exceptions.ConnectionError:
        return {"detail": "Cannot connect to API. Make sure the server is running."}, 503
    except Exception as e:
        return {"detail": f"Error: {str(e)}"}, 500


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
    
    # Settings
    st.subheader("⚙️ Settings")
    limit = st.slider("Source sentences limit", min_value=5, max_value=50, value=15)
    buffer_percentage = st.slider("Buffer percentage", min_value=10, max_value=20, value=15)
    
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
    custom_prompt = st.text_area(
        "Custom prompt (optional):",
        placeholder="E.g., Answer in bullet points",
        height=100,
        key="custom_prompt_input"
    )

# Action buttons
col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    ask_button = st.button("🔍 Ask Question", type="primary", use_container_width=True)
with col2:
    # Debug: show can_continue state
    can_continue_now = st.session_state.get("can_continue", False)
    # Calculate next level for button label
    current_level = 1
    if st.session_state.conversation_history:
        last_result = st.session_state.conversation_history[-1].get("result", {})
        current_level = last_result.get("current_level", 1)
    next_level = current_level + 1
    max_level = 20
    
    button_label = f"📚 Tell me more ({next_level}/{max_level})" if can_continue_now else "📚 Tell me more"
    continue_button = st.button(
        button_label, 
        disabled=not can_continue_now,
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
                buffer_percentage=buffer_percentage
            )
            
            if status_code == 200 and "answer" in result:
                st.session_state.session_id = result.get("session_id")
                st.session_state.can_continue = result.get("can_continue", False)
                st.session_state.conversation_history.append({
                    "type": "ask",
                    "question": user_question,
                    "result": result
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
        else:
            st.markdown(f"### 📚 Tell me more (Level {result.get('current_level', '?')})")
        
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
        
        st.markdown("**Keyword Meaning:**")
        st.text(result.get("keyword_meaning", "N/A"))
        
        # === ALWAYS VISIBLE: Source Sentences ===
        st.markdown("### 📄 Source Sentences")
        sources = result.get("source_sentences", [])
        if sources:
            for src in sources:
                level = src.get("level", 0)
                score = src.get("score", 0)
                text = src.get("text", "")
                st.markdown(f"""
                <div class="source-sentence">
                    <strong>Level {level}</strong> (Score: {score:.2f})<br>
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


# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9rem;">
    AI Chat | Powered by Elasticsearch + OpenAI | 
    <a href="http://localhost:8000/docs" target="_blank">API Docs</a>
</div>
""", unsafe_allow_html=True)
