#!/bin/bash

# watchdog.sh - Auto-restart services when they crash or hang
# This script monitors FastAPI and Streamlit processes and restarts them if needed

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CHECK_INTERVAL=30  # Check every 30 seconds
MAX_RESPONSE_TIME=10  # Maximum response time in seconds
LOG_FILE="logs/watchdog.log"
RESTART_LIMIT=5  # Maximum restarts per hour
RESTART_COUNT=0
RESTART_TIME_START=$(date +%s)

# Create log directory
mkdir -p logs

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Check if process is running
is_running() {
    local pid_file=$1
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# Check if service responds to HTTP requests
is_responsive() {
    local url=$1
    local timeout=$2
    
    if curl -s -f -m "$timeout" "$url" > /dev/null 2>&1; then
        return 0
    fi
    return 1
}

# Restart FastAPI
restart_fastapi() {
    log "${YELLOW}⚠️  Restarting FastAPI...${NC}"
    
    # Kill old process
    if [ -f "logs/fastapi.pid" ]; then
        local old_pid=$(cat logs/fastapi.pid)
        kill -9 "$old_pid" 2>/dev/null
        sleep 2
    fi
    
    # Start new process
    source venv/bin/activate
    nohup uvicorn main:app --host 0.0.0.0 --port 8000 --reload > logs/fastapi.log 2>&1 &
    local new_pid=$!
    echo $new_pid > logs/fastapi.pid
    
    log "${GREEN}✓ FastAPI restarted (PID: $new_pid)${NC}"
    
    # Wait for it to be ready
    sleep 5
    for i in {1..10}; do
        if is_responsive "http://localhost:8000/health" 5; then
            log "${GREEN}✓ FastAPI is responding${NC}"
            return 0
        fi
        sleep 2
    done
    
    log "${RED}❌ FastAPI failed to start properly${NC}"
    return 1
}

# Restart Streamlit
restart_streamlit() {
    log "${YELLOW}⚠️  Restarting Streamlit...${NC}"
    
    # Kill old process
    if [ -f "logs/streamlit.pid" ]; then
        local old_pid=$(cat logs/streamlit.pid)
        kill -9 "$old_pid" 2>/dev/null
        sleep 2
    fi
    
    # Start new process
    source venv/bin/activate
    nohup streamlit run streamlit_app.py --server.port 8501 > logs/streamlit.log 2>&1 &
    local new_pid=$!
    echo $new_pid > logs/streamlit.pid
    
    log "${GREEN}✓ Streamlit restarted (PID: $new_pid)${NC}"
    
    # Wait for it to be ready
    sleep 5
    for i in {1..10}; do
        if is_responsive "http://localhost:8501" 5; then
            log "${GREEN}✓ Streamlit is responding${NC}"
            return 0
        fi
        sleep 2
    done
    
    log "${RED}❌ Streamlit failed to start properly${NC}"
    return 1
}

# Check restart rate limit
check_restart_limit() {
    local current_time=$(date +%s)
    local time_diff=$((current_time - RESTART_TIME_START))
    
    # Reset counter if more than 1 hour has passed
    if [ $time_diff -gt 3600 ]; then
        RESTART_COUNT=0
        RESTART_TIME_START=$current_time
        return 0
    fi
    
    # Check if we've exceeded restart limit
    if [ $RESTART_COUNT -ge $RESTART_LIMIT ]; then
        log "${RED}❌ CRITICAL: Restart limit reached ($RESTART_LIMIT/hour). System is unstable!${NC}"
        log "${RED}❌ Please check logs and fix the underlying issue.${NC}"
        log "${RED}❌ Watchdog is stopping to prevent infinite restart loop.${NC}"
        return 1
    fi
    
    return 0
}

# Increment restart counter
increment_restart_count() {
    RESTART_COUNT=$((RESTART_COUNT + 1))
    log "${BLUE}ℹ️  Restart count: $RESTART_COUNT/$RESTART_LIMIT (within 1 hour)${NC}"
}

# Main monitoring loop
log "${GREEN}════════════════════════════════════════${NC}"
log "${GREEN}🔍 Watchdog started - Monitoring services${NC}"
log "${GREEN}════════════════════════════════════════${NC}"
log "Check interval: ${CHECK_INTERVAL}s"
log "Max response time: ${MAX_RESPONSE_TIME}s"
log "Restart limit: ${RESTART_LIMIT}/hour"

while true; do
    sleep $CHECK_INTERVAL
    
    # Check FastAPI
    if ! is_running "logs/fastapi.pid"; then
        log "${RED}❌ FastAPI process is not running${NC}"
        if check_restart_limit; then
            increment_restart_count
            restart_fastapi
        else
            exit 1
        fi
    elif ! is_responsive "http://localhost:8000/health" $MAX_RESPONSE_TIME; then
        log "${RED}❌ FastAPI is not responding (timeout after ${MAX_RESPONSE_TIME}s)${NC}"
        if check_restart_limit; then
            increment_restart_count
            restart_fastapi
        else
            exit 1
        fi
    else
        # Check memory usage of FastAPI
        local pid=$(cat logs/fastapi.pid)
        local mem_usage=$(ps -o %mem= -p "$pid" 2>/dev/null | tr -d ' ')
        if [ ! -z "$mem_usage" ]; then
            local mem_int=${mem_usage%.*}
            if [ $mem_int -gt 80 ]; then
                log "${YELLOW}⚠️  FastAPI high memory usage: ${mem_usage}%${NC}"
                if check_restart_limit; then
                    increment_restart_count
                    restart_fastapi
                else
                    exit 1
                fi
            fi
        fi
    fi
    
    # Check Streamlit
    if ! is_running "logs/streamlit.pid"; then
        log "${RED}❌ Streamlit process is not running${NC}"
        if check_restart_limit; then
            increment_restart_count
            restart_streamlit
        else
            exit 1
        fi
    elif ! is_responsive "http://localhost:8501" $MAX_RESPONSE_TIME; then
        log "${RED}❌ Streamlit is not responding (timeout after ${MAX_RESPONSE_TIME}s)${NC}"
        if check_restart_limit; then
            increment_restart_count
            restart_streamlit
        else
            exit 1
        fi
    fi
    
    # Log status (every 5 minutes)
    if [ $(($(date +%s) % 300)) -lt $CHECK_INTERVAL ]; then
        log "${GREEN}✓ All services running normally${NC}"
    fi
done
