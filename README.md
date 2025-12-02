# AI Vector Search Demo (Elasticsearch)

**Full-featured Q&A system** with multi-level retrieval, structured prompt builder, and "Tell me more" functionality.

## 🎯 Project Goals

Demo AI Q&A engine with:
- **Multi-level retrieval** (Level 0, 1, 2...) - gradually dive deeper into documents
- **Structured prompt builder** - clearly structured prompts
- **"Tell me more"** - allows users to explore deeper information
- **Source transparency** - always shows source sentences AI is using
- **Custom prompts** - users can add their own instructions
- **Buffer 10-20%** - retrieve extra sentences for better results

## 📁 Architecture

```
ai-vector-elastic-demo/
│── main.py                     # FastAPI app + all endpoints
│── streamlit_app.py            # Streamlit UI (web interface)
│── config.py                   # Load environment variables
│── requirements.txt            # Dependencies
│── .env                        # Environment variables (needs configuration)
│── services/
│     ├── splitter.py           # Split text into sentences
│     ├── embedder.py           # OpenAI embeddings
│     ├── retriever.py          # Multi-level retrieval from ES
│     ├── prompt_builder.py     # Build structured prompt
│     ├── session_manager.py    # Manage conversation sessions
│── vector/
│     ├── elastic_client.py     # Elasticsearch client
│── models/
│     ├── request_models.py     # Pydantic schemas
│── uploads/                    # Temporary file storage
```

## 🔄 Workflow

### 1. Upload file
```
User uploads file.txt 
    → Read content 
    → Split into sentences (sentence-level)
    → Assign levels (every 5 sentences = 1 level)
    → Create embeddings (OpenAI)
    → Store in Elasticsearch
```

### 2. Ask question (First time)
```
User asks a question
    → Create embedding for question
    → Vector search in Elasticsearch
    → Get 15 sentences, deduplicate, group by Level
    → Create 3-4 question variants
    → Extract & explain keywords
    → Build structured prompt
    → Call LLM → Get answer
    → Return session_id for continuation
```

### 3. Tell me more (Continue)
```
User clicks "Tell me more" with session_id
    → Increase level (go deeper)
    → Get NEW source sentences from deeper levels
    → Exclude previously used sentences
    → Create NEW question variants (no repeats)
    → Update keyword meanings
    → Build new prompt → Call LLM
    → Return expanded answer with new information
```

## 🛠 Setup

### 1. Create virtualenv and install dependencies

```bash
cd ai-vector-elastic-demo

python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt

# Download NLTK punkt (run once)
python -m nltk.downloader punkt punkt_tab
```

### 2. Run Elasticsearch with Docker (local)

```bash
docker run -d --name es-demo \
  -p 9200:9200 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  docker.elastic.co/elasticsearch/elasticsearch:8.15.0
```

### 3. Configure `.env`

Create `.env` file:

```env
OPENAI_API_KEY=sk-your-openai-api-key

ES_HOST=http://localhost:9200
ES_INDEX_NAME=demo_documents

# Optional
ES_USERNAME=
ES_PASSWORD=

APP_PORT=8000

EMBEDDING_MODEL=text-embedding-3-small
CHAT_MODEL=gpt-4o-mini
```

### 4. Run the API server

```bash
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

API documentation available at: http://localhost:8000/docs

### 5. Run Streamlit UI (Web Interface)

In a new terminal:

```bash
source venv/bin/activate
streamlit run streamlit_app.py
```

Streamlit UI available at: http://localhost:8501

## 🌐 Two Ways to Use

### Option 1: Streamlit UI (Recommended for demo)
- Visual web interface
- Easy file upload
- Interactive Q&A
- View source sentences and details
- URL: http://localhost:8501

### Option 2: API + Postman/Swagger
- REST API endpoints
- Full control over parameters
- Swagger docs at: http://localhost:8000/docs
- Postman collection available

## 📋 API Endpoints

### File Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/upload` | Upload and index .txt file |
| POST | `/replace` | Replace all data with new file |
| DELETE | `/documents` | Delete all documents |
| GET | `/documents/count` | Get document statistics |

### Q&A
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ask` | Ask a question, get answer + session_id |
| POST | `/continue` | Tell me more (use session_id) |

### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API information |
| GET | `/health` | Health check |

## 🔧 Request Examples

### Ask a question
```json
POST /ask
{
    "query": "What are the duties of a class teacher?",
    "custom_prompt": "Answer in bullet points",
    "limit": 15,
    "buffer_percentage": 15
}
```

### Continue conversation
```json
POST /continue
{
    "session_id": "abc-123-def",
    "custom_prompt": "Focus on specific examples",
    "buffer_percentage": 15
}
```

## ✅ Features

### 7 Main Modules
1. **File Upload** - Streaming upload to prevent RAM overflow
2. **Sentence Embeddings** - OpenAI text-embedding-3-small
3. **Query Processing** - Vector search with buffer support
4. **Deduplication** - Remove duplicate sentences
5. **Prompt Builder** - Structured prompts + custom instructions
6. **Response Generation** - GPT-4o-mini for answers
7. **Tell me more** - Session-based conversation continuation

### Additional Features
- ✅ Buffer 10-20% for better retrieval
- ✅ Custom prompts support
- ✅ Streaming file upload (1MB chunks)
- ✅ Session management (30 min timeout)
- ✅ Full Swagger documentation
- ✅ Streamlit UI for easy demo

## 🚀 Quick Start

```bash
# 1. Start Elasticsearch
docker start es-demo

# 2. Start API server
source venv/bin/activate
uvicorn main:app --reload --port 8000

# 3. Start Streamlit UI (new terminal)
source venv/bin/activate
streamlit run streamlit_app.py

# 4. Open browser
# - Streamlit: http://localhost:8501
# - Swagger: http://localhost:8000/docs
```

## 📝 License

MIT License
