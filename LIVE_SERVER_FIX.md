# 🚀 LIVE SERVER DEPLOYMENT INSTRUCTIONS

## ⚠️ IMPORTANT: Live Server is Running OLD Code

**Current Status:**
- ❌ Live server: 2 'waked'/'wakened' duplicates (OLD CODE)
- ✅ Local server: 0 duplicates (NEW CODE working)
- ✅ Code pushed to GitHub: YES

**Why live server still shows duplicates:**
Live server needs to **manually restart** - it doesn't auto-pull from GitHub.

---

## 🔧 DEPLOYMENT STEPS (Run these on LIVE SERVER)

### Step 1: SSH into live server
```bash
ssh -i your-aws-key.pem ubuntu@18.189.170.169
```

### Step 2: Navigate to project directory
```bash
cd ~/poc_elastik_new
# or wherever the project is located
```

### Step 3: Pull latest code
```bash
git pull origin main
```

### Step 4: Verify code was updated
```bash
git log --oneline -1
# Should show: "Add deploy script for live server restart"
```

### Step 5: Stop services
```bash
./stop_demo.sh
```

### Step 6: Wait 3 seconds
```bash
sleep 3
```

### Step 7: Start services with NEW code
```bash
./start_demo.sh
```

### Step 8: Wait for server to be ready
```bash
sleep 10
```

### Step 9: Verify server is running
```bash
curl http://localhost:8000/health
# Should return: {"status": "healthy", ...}
```

---

## ✅ VERIFY THE FIX WORKS

### From your LOCAL machine, run:
```bash
cd ~/poc_elastik_new
python3 test_live_dedup.py
```

### Expected output:
```
Live: ✅ PASS (max 1 'waked'/'wakened' sentence)
```

### Or test manually:
```bash
curl -X POST http://18.189.170.169:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Zechariah and the baby Jesus", "limit": 15}' \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
waked = [s for s in data['source_sentences'] if 'waked' in s['text'].lower()]
print(f'Waked/wakened sentences: {len(waked)}')
print(f'Status: {\"✅ PASS\" if len(waked) <= 1 else \"❌ FAIL\"}')"
```

---

## 📋 ONE-LINER (Run all at once on live server)

```bash
cd ~/poc_elastik_new && git pull origin main && ./stop_demo.sh && sleep 3 && ./start_demo.sh
```

---

## 🐛 If something goes wrong:

### Check logs:
```bash
tail -100 logs/app.log
tail -50 logs/fastapi.log
```

### Restart everything:
```bash
./stop_demo.sh
rm logs/*.log  # Clear logs
./start_demo.sh
```

### Rollback to previous version (if needed):
```bash
git revert HEAD
./stop_demo.sh
./start_demo.sh
```

---

## 📊 What changed in the code

Files modified:
- `services/deduplicator.py` - Added fuzzy similarity matching
- `services/multi_level_retriever.py` - Applied deduplication at all levels

Behavior change:
- **Before**: Only removes exact duplicates
- **After**: Removes exact + near-duplicates (>95% similar, like "waked" vs "wakened")

---

## ❓ Questions?

Check these files for details:
- `FIX_DEDUPLICATION.md` - Detailed explanation of the fix
- `test_live_dedup.py` - Test script to verify fix
- `DEPLOYMENT_LIVE.md` - Alternative deployment guide
