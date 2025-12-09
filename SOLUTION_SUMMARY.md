# ✅ GIẢI PHÁP: Large Requests & Auto-Restart

## 🎯 Vấn Đề Đã Giải Quyết

### 1. **Large Request Crashes**
**Vấn đề:** Server crash khi request quá lớn hoặc nhiều người dùng cùng lúc
**Giải pháp:**
- ✅ Giới hạn request size: **10MB maximum**
- ✅ Timeout cho requests: **10 phút** (normal), **15 phút** (complex queries)
- ✅ LLM timeout: **5 phút** với retry logic
- ✅ Upload timeout: **1 giờ** cho files lớn
- ✅ Middleware tự động reject requests quá lớn
- ✅ Error messages rõ ràng cho users

### 2. **Server Crash & Hang**
**Vấn đề:** Server crash hoặc hang, phải restart thủ công
**Giải pháp:**
- ✅ **Watchdog auto-restart** - tự động restart khi:
  - Process bị kill/crash
  - Server không respond (hang)
  - Memory usage > 80%
- ✅ Health check mỗi **30 giây**
- ✅ Auto-restart trong vòng **30-60 giây**
- ✅ Rate limit: Max **5 restarts/hour** (tránh infinite loop)
- ✅ Full logging cho troubleshooting

### 3. **Concurrent Users**
**Vấn đề:** Nhiều users cùng lúc làm crash server
**Giải pháp:**
- ✅ Async request handling
- ✅ Client disconnect detection
- ✅ Timeout middleware cho mỗi request riêng biệt
- ✅ LLM retry với exponential backoff

## 🚀 Cách Sử Dụng

### Start Server (với Auto-Restart)
```bash
./start_demo.sh
```

Server sẽ tự động:
- Start FastAPI on port 8000
- Start Streamlit on port 8501
- Start ngrok tunnel
- **Start watchdog để monitor & auto-restart**

### Stop Server
```bash
./stop_demo.sh
```

Dừng tất cả services bao gồm watchdog.

### Monitor Logs
```bash
# Xem watchdog activity (restarts, health checks)
tail -f logs/watchdog.log

# Xem API errors
tail -f logs/fastapi.log

# Xem UI errors  
tail -f logs/streamlit.log
```

## 📊 Chi Tiết Kỹ Thuật

### 1. Request Limits & Timeouts (config.py)
```python
MAX_REQUEST_SIZE = 10MB        # Max request body size
REQUEST_TIMEOUT = 600s         # Normal request timeout
LLM_TIMEOUT = 300s            # LLM API call timeout
UPLOAD_TIMEOUT = 3600s        # File upload timeout
```

### 2. Middleware Protection (main.py)
- **RequestSizeLimitMiddleware**: Reject requests > 10MB
- **TimeoutMiddleware**: Auto-timeout long requests
- **ClientDisconnect handling**: Không crash khi user disconnect
- **Signal handlers**: Graceful shutdown on SIGTERM/SIGINT

### 3. LLM Retry Logic (services/prompt_builder.py)
```python
- Max 3 retries cho timeouts/rate limits
- Exponential backoff: 2s, 4s, 6s
- Clear error messages cho users
```

### 4. Watchdog Auto-Restart (watchdog.sh)
```bash
- Check every 30 seconds
- Health check timeout: 10 seconds
- Memory threshold: 80%
- Max restarts: 5 per hour
- Auto-restart trong 30-60 giây
```

### 5. Error Messages (streamlit_app.py)
- Connection errors → "Server may have crashed, check logs"
- Timeouts → "Try shorter prompt or disable some levels"
- Large files → Shows estimated time, no timeout

## 🧪 Testing

### Test Auto-Restart
```bash
# Test 1: Kill process manually
kill $(cat logs/fastapi.pid)
# Watchdog sẽ restart trong 30-60s

# Test 2: Check logs
tail -f logs/watchdog.log
# Sẽ thấy: "⚠️ Restarting FastAPI..." → "✓ FastAPI restarted"
```

### Test Large Request Protection
```bash
# Upload file > 200MB → Rejected with clear error
# Query với huge custom prompt → Timeout after 10-15 min with error message
```

### Run All Tests
```bash
./test_stability.sh
```

## 📋 Monitoring & Troubleshooting

### Check Status
```bash
# Check if all services running
curl http://localhost:8000/health
curl http://localhost:8501

# Check watchdog status
ps aux | grep watchdog.sh
```

### Common Issues

**Server keeps crashing (>5 times/hour)**
→ Watchdog stops to prevent infinite loop
→ Check `logs/watchdog.log` for pattern
→ Fix root cause (e.g., Elasticsearch down, memory leak)
→ Manually restart: `./stop_demo.sh && ./start_demo.sh`

**Timeout errors frequently**
→ Reduce custom prompt length
→ Disable some levels (Level 2, 3)
→ Check network/LLM API status

**High memory usage**
→ Watchdog auto-restarts at 80%
→ Check `logs/watchdog.log` for memory restarts
→ Consider increasing server RAM

## ✅ Benefits

### Before (Trước đây)
❌ Crash khi request quá lớn
❌ Hang khi nhiều users cùng lúc
❌ Phải restart thủ công
❌ Không rõ tại sao crash
❌ Downtime kéo dài

### After (Bây giờ)
✅ Reject requests quá lớn với error rõ ràng
✅ Handle concurrent users safely
✅ **Auto-restart trong 30-60 giây**
✅ Full logging cho troubleshooting
✅ **Minimal downtime** (~1 minute max)
✅ Rate limiting prevents infinite loops
✅ Clear error messages cho users

## 🎯 Kết Luận

Hệ thống đã được cải thiện để:
1. **Không crash** với large requests
2. **Tự động restart** khi có vấn đề
3. **Handle concurrent users** an toàn
4. **Clear error messages** thay vì crash
5. **Production-ready** với monitoring & auto-recovery

### Files Changed
- `config.py` - Added timeout configs
- `main.py` - Added middlewares, signal handlers
- `services/prompt_builder.py` - Added retry logic
- `services/session_manager.py` - Added cleanup
- `streamlit_app.py` - Improved error handling
- `watchdog.sh` - **NEW** Auto-restart script
- `start_demo.sh` - Auto-start watchdog
- `stop_demo.sh` - Stop watchdog properly
- `test_stability.sh` - **NEW** Verification tests
- `AUTO_RESTART_README.md` - **NEW** Full documentation

### Quick Start
```bash
# Test everything works
./test_stability.sh

# Start with auto-restart
./start_demo.sh

# Monitor
tail -f logs/watchdog.log

# Stop everything
./stop_demo.sh
```

**Hệ thống giờ đã stable và tự động recover khi có vấn đề!** 🎉
