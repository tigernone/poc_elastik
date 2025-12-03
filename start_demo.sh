#!/bin/bash

# start_demo.sh - Script to start all services for demo

echo "🚀 Starting AI Vector Elastic Demo..."
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Activate virtual environment
if [ -d "venv" ]; then
    echo -e "${BLUE}🐍 Activating virtual environment...${NC}"
    source venv/bin/activate
    echo -e "${GREEN}✓ Virtual environment activated${NC}"
    echo ""
else
    echo -e "${YELLOW}⚠️  Warning: venv directory not found!${NC}"
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  Warning: .env file not found!${NC}"
    echo "Please create .env file with your API keys"
    exit 1
fi

# Check if Elasticsearch is running
echo -e "${BLUE}🔍 Checking Elasticsearch...${NC}"
if curl -s http://localhost:9200 > /dev/null; then
    echo -e "${GREEN}✓ Elasticsearch is running${NC}"
else
    echo -e "${YELLOW}⚠️  Elasticsearch is not running on port 9200${NC}"
    echo "Please start Elasticsearch first"
    exit 1
fi

echo ""
echo -e "${BLUE}📦 Checking dependencies...${NC}"
pip install -q -r requirements.txt
echo -e "${GREEN}✓ Dependencies ready${NC}"
echo ""

# Create log directory
mkdir -p logs

# Start FastAPI server
echo -e "${BLUE}🔧 Starting FastAPI server on port 8000...${NC}"
nohup uvicorn main:app --host 0.0.0.0 --port 8000 --reload > logs/fastapi.log 2>&1 &
FASTAPI_PID=$!
echo $FASTAPI_PID > logs/fastapi.pid
echo -e "${GREEN}✓ FastAPI started (PID: $FASTAPI_PID)${NC}"

# Wait for FastAPI to start
sleep 3

# Start Streamlit app
echo -e "${BLUE}🎨 Starting Streamlit app on port 8501...${NC}"
streamlit run streamlit_app.py --server.port 8501 > logs/streamlit.log 2>&1 &
STREAMLIT_PID=$!
echo $STREAMLIT_PID > logs/streamlit.pid
echo -e "${GREEN}✓ Streamlit started (PID: $STREAMLIT_PID)${NC}"

# Wait for Streamlit to start and be ready
echo -e "${BLUE}⏳ Waiting for Streamlit to be ready...${NC}"
sleep 3
for i in {1..15}; do
    if curl -s http://localhost:8501 > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Streamlit is ready!${NC}"
        break
    fi
    echo -n "."
    sleep 1
done
echo ""

echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ All services started successfully!${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo -e "${BLUE}📍 Local URLs:${NC}"
echo "   FastAPI:   http://localhost:8000"
echo "   Streamlit: http://localhost:8501"
echo ""
echo -e "${BLUE}🌐 Starting ngrok tunnel...${NC}"
echo ""

# Check if ngrok is installed
if ! command -v ngrok &> /dev/null; then
    echo -e "${YELLOW}⚠️  ngrok is not installed${NC}"
    echo "Please install ngrok from: https://ngrok.com/download"
    echo ""
    echo "Or install via Homebrew:"
    echo "  brew install ngrok"
    echo ""
    echo -e "${BLUE}Services are running locally at:${NC}"
    echo "  http://localhost:8501"
    exit 0
fi

# Start ngrok for Streamlit
echo -e "${BLUE}Starting ngrok tunnel for Streamlit...${NC}"
nohup ngrok http 8501 > logs/ngrok.log 2>&1 &
NGROK_PID=$!
echo $NGROK_PID > logs/ngrok.pid

# Wait for ngrok to start
sleep 3

# Get ngrok public URL
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | grep -o '"public_url":"https://[^"]*' | grep -o 'https://[^"]*' | head -1)

echo ""
if [ ! -z "$NGROK_URL" ]; then
    echo -e "${GREEN}════════════════════════════════════════${NC}"
    echo -e "${GREEN}🎉 Demo is ready!${NC}"
    echo -e "${GREEN}════════════════════════════════════════${NC}"
    echo ""
    echo -e "${BLUE}📱 Share this URL with your client:${NC}"
    echo -e "${GREEN}${NGROK_URL}${NC}"
    echo ""
else
    echo -e "${YELLOW}⚠️  Could not get ngrok URL${NC}"
    echo "Check logs/ngrok.log for details"
    echo ""
    echo -e "${BLUE}Local URL:${NC}"
    echo "http://localhost:8501"
fi

echo ""
echo -e "${BLUE}📊 Logs:${NC}"
echo "   FastAPI:   logs/fastapi.log"
echo "   Streamlit: logs/streamlit.log"
echo "   ngrok:     logs/ngrok.log"
echo ""
echo -e "${BLUE}To stop all services:${NC}"
echo "   ./stop_demo.sh"
echo ""
