#!/bin/bash
# ===========================================
# DEPLOY SCRIPT - AI Vector Search Demo
# ===========================================
# This script starts all services and exposes them via ngrok
# for client testing.

set -e

PROJECT_DIR="/Users/minknguyen/Desktop/Working/POC/ai-vector-elastic-demo"
cd "$PROJECT_DIR"

echo "=============================================="
echo "   AI Vector Search Demo - Deployment Script"
echo "=============================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if port is in use
check_port() {
    lsof -i:$1 > /dev/null 2>&1
}

# 1. Check/Start Elasticsearch
echo -e "${YELLOW}[1/4] Checking Elasticsearch...${NC}"
if curl -s http://localhost:9200 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Elasticsearch is running${NC}"
else
    echo "Starting Elasticsearch..."
    docker start es-demo 2>/dev/null || docker run -d --name es-demo \
        -p 9200:9200 -p 9300:9300 \
        -e "discovery.type=single-node" \
        -e "xpack.security.enabled=false" \
        docker.elastic.co/elasticsearch/elasticsearch:8.15.0
    sleep 10
    echo -e "${GREEN}✅ Elasticsearch started${NC}"
fi

# 2. Start FastAPI
echo -e "${YELLOW}[2/4] Starting FastAPI server...${NC}"
pkill -f "uvicorn main:app" 2>/dev/null || true
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
sleep 1

nohup ./venv/bin/python -m uvicorn main:app --port 8000 --host 0.0.0.0 > /tmp/fastapi.log 2>&1 &
sleep 3

if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ FastAPI is running on port 8000${NC}"
else
    echo -e "${RED}❌ FastAPI failed to start. Check /tmp/fastapi.log${NC}"
    exit 1
fi

# 3. Start Streamlit
echo -e "${YELLOW}[3/4] Starting Streamlit...${NC}"
pkill -f "streamlit run" 2>/dev/null || true
lsof -ti:8501 | xargs kill -9 2>/dev/null || true
sleep 1

mkdir -p ~/.streamlit
echo '[general]
email = ""' > ~/.streamlit/credentials.toml

nohup ./venv/bin/python -m streamlit run streamlit_app.py --server.port 8501 --server.headless true > /tmp/streamlit.log 2>&1 &
sleep 3

if curl -s http://localhost:8501 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Streamlit is running on port 8501${NC}"
else
    echo -e "${RED}❌ Streamlit failed to start. Check /tmp/streamlit.log${NC}"
    exit 1
fi

# 4. Check ngrok
echo -e "${YELLOW}[4/4] Setting up ngrok for public access...${NC}"

if ! command -v ngrok &> /dev/null; then
    echo "Installing ngrok..."
    brew install ngrok/ngrok/ngrok 2>/dev/null || {
        echo -e "${RED}Please install ngrok manually:${NC}"
        echo "  brew install ngrok/ngrok/ngrok"
        echo "  OR download from https://ngrok.com/download"
        echo ""
        echo -e "${GREEN}Local URLs (for now):${NC}"
        echo "  Streamlit UI: http://localhost:8501"
        echo "  API Swagger:  http://localhost:8000/docs"
        exit 0
    }
fi

# Kill existing ngrok
pkill -f ngrok 2>/dev/null || true
sleep 1

echo ""
echo "=============================================="
echo -e "${GREEN}   ✅ ALL SERVICES STARTED SUCCESSFULLY!${NC}"
echo "=============================================="
echo ""
echo "📍 LOCAL ACCESS:"
echo "   Streamlit UI: http://localhost:8501"
echo "   API Swagger:  http://localhost:8000/docs"
echo "   API Health:   http://localhost:8000/health"
echo ""
echo "🌐 TO SHARE WITH CLIENT:"
echo "   Run this command in a new terminal:"
echo ""
echo "   ngrok http 8501"
echo ""
echo "   This will give you a public URL like:"
echo "   https://xxxx-xx-xx-xxx-xxx.ngrok-free.app"
echo ""
echo "   Share that URL with your client!"
echo ""
echo "=============================================="
