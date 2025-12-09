#!/bin/bash
# Script để deploy code mới trên live server
# Chạy script này trên LIVE SERVER (SSH vào nó rồi chạy)

set -e  # Exit on error

echo "=========================================="
echo "🚀 DEPLOYING NEW CODE ON LIVE SERVER"
echo "=========================================="

# Get to project directory
cd /home/ubuntu/poc_elastik_new || cd ~/poc_elastik_new || cd $(pwd)

echo ""
echo "1️⃣  Current directory: $(pwd)"
echo ""

# Check git status
echo "2️⃣  Checking git status before pull..."
git status

echo ""
echo "3️⃣  Pulling latest code from GitHub..."
git pull origin main

echo ""
echo "4️⃣  Verifying code changes..."
git log --oneline -3

echo ""
echo "5️⃣  Stopping current services..."
./stop_demo.sh

echo ""
echo "6️⃣  Waiting 5 seconds..."
sleep 5

echo ""
echo "7️⃣  Starting services with NEW code..."
./start_demo.sh

echo ""
echo "8️⃣  Waiting 10 seconds for services to start..."
sleep 10

echo ""
echo "9️⃣  Verifying server is running..."
curl -s http://localhost:8000/health | python3 -m json.tool || echo "Health check failed"

echo ""
echo "=========================================="
echo "✅ DEPLOYMENT COMPLETE"
echo "=========================================="
echo ""
echo "Test with:"
echo 'curl -X POST http://localhost:8000/ask \\'
echo '  -H "Content-Type: application/json" \\'
echo '  -d "{\"query\": \"Zechariah and the baby Jesus\", \"limit\": 15}"'
echo ""
echo "Expected: Only 1 (or 0) sentence with 'waked'/'wakened'"
echo ""
