#!/bin/bash

# stop_demo.sh - Script to stop all demo services

echo "🛑 Stopping all demo services..."

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Function to stop a service
stop_service() {
    SERVICE_NAME=$1
    PID_FILE=$2
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            kill $PID 2>/dev/null
            echo -e "${GREEN}✓ Stopped $SERVICE_NAME (PID: $PID)${NC}"
        else
            echo -e "${RED}✗ $SERVICE_NAME was not running${NC}"
        fi
        rm "$PID_FILE"
    else
        echo -e "${RED}✗ No PID file found for $SERVICE_NAME${NC}"
    fi
}

# Stop all services
stop_service "FastAPI" "logs/fastapi.pid"
stop_service "Streamlit" "logs/streamlit.pid"
stop_service "ngrok" "logs/ngrok.pid"

# Also kill any remaining processes
echo ""
echo "Cleaning up any remaining processes..."

# Kill any remaining uvicorn processes
pkill -f "uvicorn main:app" 2>/dev/null && echo -e "${GREEN}✓ Cleaned up uvicorn processes${NC}"

# Kill any remaining streamlit processes
pkill -f "streamlit run" 2>/dev/null && echo -e "${GREEN}✓ Cleaned up streamlit processes${NC}"

# Kill any remaining ngrok processes on port 8501
pkill -f "ngrok http 8501" 2>/dev/null && echo -e "${GREEN}✓ Cleaned up ngrok processes${NC}"

echo ""
echo -e "${GREEN}✓ All services stopped${NC}"
