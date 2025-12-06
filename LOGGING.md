# Logging Guide

## Log Files

All logs are stored in the `logs/` directory:

- **`logs/app.log`** - Main application logs (API requests, keyword extraction, retrieval)
- **`logs/fastapi.log`** - FastAPI server logs
- **`logs/streamlit.log`** - Streamlit UI logs  
- **`logs/ngrok.log`** - Ngrok tunnel logs

## Log Levels

- **INFO**: Normal operations (API requests, successful retrievals)
- **WARNING**: Issues that don't break functionality (fallback to old method)
- **ERROR**: Errors in search, LLM calls, etc.
- **DEBUG**: Detailed ES queries, search parameters

## Key Log Entries

### API Requests
```
[API /ask] New request - query='...', limit=10
[API /ask] Extracted keywords: ['lord', 'faith', 'woman']
[API /ask] Retrieved 5 source sentences
```

### Keyword Extraction
```
[KeywordExtractor] Extracting keywords from: ...
[KeywordExtractor] LLM response: ["lord", "faith", "woman"]
[KeywordExtractor] Extracted keywords: ['lord', 'faith', 'woman']
```

### Multi-level Retrieval
```
[Level 0] Starting search - offset=0, limit=10, used_texts=0
[ES Query] query_text='lord faith...', match_type=multi_match, require_all_words=True
[ES Results] Found 4 results for query 'lord faith...'
```

### Search Details
```
[Level 1] Searching for keyword: 'faith' (offset=0/3)
[ES Results] Found 10 results for query 'faith'
```

## Viewing Logs

### Real-time monitoring
```bash
# Watch all API logs
tail -f logs/app.log

# Watch with filtering
tail -f logs/app.log | grep "\[API"

# Watch errors only
tail -f logs/app.log | grep "ERROR"
```

### Search logs
```bash
# Find all keyword extraction logs
grep "KeywordExtractor" logs/app.log

# Find retrieval statistics
grep "Retrieved.*sentences" logs/app.log

# Find errors
grep "ERROR" logs/app.log
```

## Testing Logging

Run the test script:
```bash
python3 test_logging.py
```

## Log Rotation

Logs are automatically managed by the system. To clear logs:
```bash
# Clear all logs
rm logs/*.log

# Or selectively
rm logs/app.log
```

## Debugging Tips

1. **Keyword extraction issues**: Look for `[KeywordExtractor]` entries
2. **No results returned**: Check `[ES Results] Found 0 results`
3. **Performance issues**: Count ES queries and check timings
4. **API errors**: Search for `ERROR` or `WARNING` levels

## Git Ignore

Logs are automatically excluded from git via `.gitignore`:
```
logs/
*.log
app.log
fastapi.log
streamlit.log
ngrok.log
```
