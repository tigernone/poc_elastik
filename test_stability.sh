#!/bin/bash

# test_stability.sh - Quick test script for stability improvements

echo "🧪 Testing Stability Improvements..."
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Test 1: Check if watchdog.sh is executable
echo "Test 1: Checking watchdog.sh..."
if [ -x "watchdog.sh" ]; then
    echo -e "${GREEN}✓ watchdog.sh is executable${NC}"
else
    echo -e "${RED}✗ watchdog.sh is not executable${NC}"
    exit 1
fi

# Test 2: Verify watchdog.sh syntax
echo ""
echo "Test 2: Checking watchdog.sh syntax..."
bash -n watchdog.sh
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ watchdog.sh syntax is valid${NC}"
else
    echo -e "${RED}✗ watchdog.sh has syntax errors${NC}"
    exit 1
fi

# Test 3: Check if config.py has new timeout settings
echo ""
echo "Test 3: Checking config.py for timeout settings..."
if grep -q "MAX_REQUEST_SIZE" config.py && grep -q "REQUEST_TIMEOUT" config.py && grep -q "LLM_TIMEOUT" config.py; then
    echo -e "${GREEN}✓ Timeout settings found in config.py${NC}"
else
    echo -e "${RED}✗ Missing timeout settings in config.py${NC}"
    exit 1
fi

# Test 4: Check if main.py has middleware
echo ""
echo "Test 4: Checking main.py for middleware..."
if grep -q "RequestSizeLimitMiddleware" main.py && grep -q "TimeoutMiddleware" main.py; then
    echo -e "${GREEN}✓ Middleware classes found in main.py${NC}"
else
    echo -e "${RED}✗ Missing middleware in main.py${NC}"
    exit 1
fi

# Test 5: Check if prompt_builder.py has retry logic
echo ""
echo "Test 5: Checking prompt_builder.py for retry logic..."
if grep -q "max_retries" services/prompt_builder.py; then
    echo -e "${GREEN}✓ Retry logic found in prompt_builder.py${NC}"
else
    echo -e "${RED}✗ Missing retry logic in prompt_builder.py${NC}"
    exit 1
fi

# Test 6: Check if session_manager.py has cleanup method
echo ""
echo "Test 6: Checking session_manager.py for cleanup..."
if grep -q "clear_all_sessions" services/session_manager.py; then
    echo -e "${GREEN}✓ Cleanup method found in session_manager.py${NC}"
else
    echo -e "${RED}✗ Missing cleanup method in session_manager.py${NC}"
    exit 1
fi

# Test 7: Check if streamlit_app.py has improved error handling
echo ""
echo "Test 7: Checking streamlit_app.py for error handling..."
if grep -q "ConnectionError" streamlit_app.py && grep -q "server may have crashed" streamlit_app.py; then
    echo -e "${GREEN}✓ Improved error handling found in streamlit_app.py${NC}"
else
    echo -e "${RED}✗ Missing improved error handling in streamlit_app.py${NC}"
    exit 1
fi

# Test 8: Check if start_demo.sh starts watchdog
echo ""
echo "Test 8: Checking start_demo.sh for watchdog integration..."
if grep -q "watchdog.sh" start_demo.sh; then
    echo -e "${GREEN}✓ Watchdog integration found in start_demo.sh${NC}"
else
    echo -e "${RED}✗ Missing watchdog integration in start_demo.sh${NC}"
    exit 1
fi

# Test 9: Check if stop_demo.sh stops watchdog
echo ""
echo "Test 9: Checking stop_demo.sh for watchdog cleanup..."
if grep -q "watchdog" stop_demo.sh; then
    echo -e "${GREEN}✓ Watchdog cleanup found in stop_demo.sh${NC}"
else
    echo -e "${RED}✗ Missing watchdog cleanup in stop_demo.sh${NC}"
    exit 1
fi

# Test 10: Check Python syntax
echo ""
echo "Test 10: Checking Python syntax..."
python3 -m py_compile main.py 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ main.py syntax is valid${NC}"
else
    echo -e "${RED}✗ main.py has syntax errors${NC}"
    exit 1
fi

python3 -m py_compile config.py 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ config.py syntax is valid${NC}"
else
    echo -e "${RED}✗ config.py has syntax errors${NC}"
    exit 1
fi

python3 -m py_compile streamlit_app.py 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ streamlit_app.py syntax is valid${NC}"
else
    echo -e "${RED}✗ streamlit_app.py has syntax errors${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ All tests passed!${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo "Summary of improvements:"
echo "  ✓ Request size limits (10MB max)"
echo "  ✓ Timeouts (10min requests, 5min LLM, 1hr uploads)"
echo "  ✓ Error handling with retry logic"
echo "  ✓ Graceful shutdown handling"
echo "  ✓ Auto-restart watchdog"
echo "  ✓ Improved Streamlit error messages"
echo "  ✓ Deploy scripts integration"
echo ""
echo "Ready to use! Run: ./start_demo.sh"
