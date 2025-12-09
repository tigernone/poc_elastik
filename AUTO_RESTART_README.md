# Auto-Restart & Stability Improvements

## 🔧 Changes Made

### 1. **Request Size Limits & Timeouts** (config.py, main.py)
- ✅ Added `MAX_REQUEST_SIZE`: 10MB limit for request bodies
- ✅ Added `REQUEST_TIMEOUT`: 10 minutes for normal requests
- ✅ Added `LLM_TIMEOUT`: 5 minutes for LLM API calls
- ✅ Added `UPLOAD_TIMEOUT`: 1 hour for large file uploads
- ✅ Implemented middleware to enforce these limits

### 2. **Error Handling & Recovery** (main.py, services/)
- ✅ Added comprehensive try-catch with retry logic for LLM calls
- ✅ Exponential backoff for rate limits and timeouts
- ✅ Graceful handling of client disconnects
- ✅ Proper error messages returned to users
- ✅ Session cleanup on shutdown

### 3. **Watchdog Auto-Restart System** (watchdog.sh)
- ✅ Monitors FastAPI and Streamlit processes every 30 seconds
- ✅ Checks if processes are running
- ✅ Checks if services respond to HTTP requests (health check)
- ✅ Monitors memory usage (restarts if >80%)
- ✅ Auto-restarts crashed or hanging services
- ✅ Rate limiting: Max 5 restarts per hour (prevents infinite loops)
- ✅ Detailed logging to `logs/watchdog.log`

### 4. **Improved Streamlit Error Handling** (streamlit_app.py)
- ✅ Better timeout messages with actionable suggestions
- ✅ Connection error detection and helpful messages
- ✅ File size estimation for uploads
- ✅ Adaptive timeouts based on request complexity

### 5. **Updated Deploy Scripts** (start_demo.sh, stop_demo.sh)
- ✅ Automatically starts watchdog when demo starts
- ✅ Properly stops watchdog when demo stops
- ✅ Shows watchdog status and configuration

## 🚀 How to Use

### Starting the Demo with Auto-Restart
```bash
./start_demo.sh
```

The watchdog will automatically:
- Start monitoring after 3 seconds
- Check services every 30 seconds
- Restart crashed services immediately
- Log all activities to `logs/watchdog.log`

### Stopping Everything
```bash
./stop_demo.sh
```

This will stop:
- Watchdog process
- FastAPI server
- Streamlit app
- ngrok tunnel

### Monitoring Logs
```bash
# Watch watchdog activity
tail -f logs/watchdog.log

# Watch FastAPI logs
tail -f logs/fastapi.log

# Watch Streamlit logs
tail -f logs/streamlit.log
```

## 🔍 Watchdog Features

### Health Checks
- **Process Check**: Verifies PID is still running
- **HTTP Check**: Tests if service responds (10s timeout)
- **Memory Check**: Monitors RAM usage (restarts if >80%)

### Auto-Restart Logic
1. Detects problem (crash, hang, high memory)
2. Checks restart rate limit (5/hour max)
3. Kills old process gracefully
4. Starts new process
5. Waits for service to be ready (up to 20 seconds)
6. Logs success or failure

### Safety Features
- **Rate Limiting**: Max 5 restarts per hour to prevent infinite restart loops
- **Timeout Protection**: Stops trying after 20 seconds if service won't start
- **Graceful Shutdown**: Cleans up properly when stopped

## 📊 Configuration

Edit `watchdog.sh` to customize:
```bash
CHECK_INTERVAL=30          # Check every 30 seconds
MAX_RESPONSE_TIME=10       # Max 10s for health check
RESTART_LIMIT=5            # Max 5 restarts per hour
```

## 🐛 Troubleshooting

### If Services Keep Crashing
1. Check logs: `tail -f logs/watchdog.log`
2. Look for error patterns in `logs/fastapi.log`
3. Verify Elasticsearch is running: `curl http://localhost:9200`
4. Check disk space: `df -h`
5. Check memory: `free -h` (Linux) or `vm_stat` (Mac)

### If Watchdog Stops
This means restart limit was reached (5/hour). This is intentional to prevent infinite loops.

**What to do:**
1. Check logs to find root cause
2. Fix the underlying issue (e.g., Elasticsearch down, memory leak, etc.)
3. Wait 1 hour for counter to reset, OR
4. Manually restart: `./stop_demo.sh && ./start_demo.sh`

### Common Issues

**Large Request Crashes:**
- Now protected by 10MB request size limit
- Timeout after 10 minutes for normal requests
- LLM calls timeout after 5 minutes with retry

**Concurrent Users:**
- Each request runs in its own async context
- Middleware prevents one slow request from blocking others
- Client disconnect is handled gracefully

**Memory Issues:**
- Watchdog monitors memory usage
- Auto-restarts if process uses >80% RAM
- File uploads use streaming to prevent RAM overflow

## 📝 Environment Variables

Add these to your `.env` if you want to customize (optional):
```bash
# Request limits (already in config.py with defaults)
MAX_REQUEST_SIZE=10485760      # 10MB in bytes
REQUEST_TIMEOUT=600            # 10 minutes
LLM_TIMEOUT=300                # 5 minutes  
UPLOAD_TIMEOUT=3600            # 1 hour
```

## ✅ Testing the Auto-Restart

### Test 1: Process Kill
```bash
# Kill FastAPI manually
kill $(cat logs/fastapi.pid)

# Watch watchdog restart it
tail -f logs/watchdog.log
```

Within 30 seconds, watchdog should detect and restart FastAPI.

### Test 2: Hanging Process
```bash
# Send STOP signal to hang the process
kill -STOP $(cat logs/streamlit.pid)

# Watchdog will detect it's not responding and restart
```

### Test 3: Large Request
Try uploading a very large file or sending a huge custom prompt. The system will:
1. Return proper error if too large (>10MB)
2. Timeout gracefully if taking too long
3. Not crash the server

## 🎯 Benefits

✅ **No More Manual Restarts**: Server auto-recovers from crashes
✅ **Better User Experience**: Clear error messages instead of crashes
✅ **Safer Operations**: Rate limiting prevents infinite restart loops
✅ **Easy Monitoring**: All activities logged clearly
✅ **Production Ready**: Handles concurrent users and large requests safely

## 📞 Support

If you encounter issues:
1. Check `logs/watchdog.log` for restart history
2. Check `logs/fastapi.log` for API errors
3. Check `logs/streamlit.log` for UI errors
4. Verify all dependencies: `pip install -r requirements.txt`
5. Restart from scratch: `./stop_demo.sh && ./start_demo.sh`
