#!/usr/bin/env python3
"""
Test Suite for Multi-Level Retrieval System
============================================

Run: python tests/test_multilevel.py

Tests:
1. Keyword extraction + magic words filtering
2. Each level retrieval independently
3. Session state & deduplication
4. End-to-end flow
"""
import os
import sys
import json
import requests
from typing import List, Dict, Any
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

# Config
API_BASE = "http://localhost:8000"
TEST_CORPUS = PROJECT_ROOT / "test_data" / "test_corpus.txt"

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")

def print_pass(text: str):
    print(f"{Colors.GREEN}✅ PASS: {text}{Colors.END}")

def print_fail(text: str):
    print(f"{Colors.RED}❌ FAIL: {text}{Colors.END}")

def print_info(text: str):
    print(f"{Colors.YELLOW}ℹ️  {text}{Colors.END}")


# =============================================================================
# TEST 1: Keyword Extraction + Magic Words Filtering
# =============================================================================

def test_keyword_extraction():
    """Test that keywords are extracted correctly and magic words filtered"""
    print_header("TEST 1: Keyword Extraction + Magic Words Filtering")
    
    from services.keyword_extractor import (
        extract_keywords_raw,
        filter_magic_words,
        extract_keywords,
        MAGIC_WORDS
    )
    
    print_info(f"Loaded {len(MAGIC_WORDS)} magic words")
    
    test_queries = [
        "How does grace unlock spiritual freedom?",
        "Explain how God's grace is connected to freedom.",
        "What is the meaning of salvation?",
        "Why is faith important for believers?",
    ]
    
    all_passed = True
    
    for query in test_queries:
        print(f"\n📝 Query: '{query}'")
        
        raw = extract_keywords_raw(query)
        filtered = filter_magic_words(raw)
        final = extract_keywords(query)
        
        print(f"   Raw keywords: {raw}")
        print(f"   After filter: {filtered}")
        print(f"   Final result: {final}")
        
        # Check that magic words are filtered
        magic_in_result = [w for w in final if w.lower() in MAGIC_WORDS]
        if magic_in_result:
            print_fail(f"Magic words found in result: {magic_in_result}")
            all_passed = False
        else:
            print_pass("No magic words in result")
        
        # Check that we have meaningful keywords
        if len(final) == 0:
            print_fail("No keywords extracted!")
            all_passed = False
        elif len(final) > 0:
            print_pass(f"Extracted {len(final)} keywords")
    
    return all_passed


# =============================================================================
# TEST 2: Each Level Retrieval Independently
# =============================================================================

def test_level_retrieval():
    """Test each level's retrieval function independently"""
    print_header("TEST 2: Level Retrieval (Level 0, 1, 2, 3)")
    
    from services.keyword_extractor import extract_keywords
    from services.multi_level_retriever import MultiLevelRetriever
    
    # Test keywords
    test_query = "How does grace unlock freedom?"
    keywords = extract_keywords(test_query)
    
    if not keywords:
        keywords = ["grace", "freedom"]  # Fallback
    
    print_info(f"Testing with keywords: {keywords}")
    
    retriever = MultiLevelRetriever(keywords)
    all_passed = True
    used_texts = set()
    
    # Test Level 0
    print(f"\n{Colors.BOLD}--- Level 0: Keyword Combinations ---{Colors.END}")
    sentences_0, offset_0, exhausted_0 = retriever.fetch_level0_sentences(
        offset=0, limit=5, used_texts=used_texts
    )
    print(f"   Found: {len(sentences_0)} sentences")
    print(f"   Offset: {offset_0}, Exhausted: {exhausted_0}")
    for s in sentences_0[:3]:
        print(f"   - [{s['level']}] {s['text'][:60]}...")
        used_texts.add(s['text'])
    
    if len(sentences_0) > 0:
        print_pass("Level 0 returned sentences")
    else:
        print_fail("Level 0 returned no sentences")
        all_passed = False
    
    # Test Level 1
    print(f"\n{Colors.BOLD}--- Level 1: Single Keywords ---{Colors.END}")
    sentences_1, offset_1, exhausted_1 = retriever.fetch_level1_sentences(
        offset=0, limit=5, used_texts=used_texts
    )
    print(f"   Found: {len(sentences_1)} sentences")
    print(f"   Offset: {offset_1}, Exhausted: {exhausted_1}")
    for s in sentences_1[:3]:
        print(f"   - [{s['level']}] {s['text'][:60]}...")
        used_texts.add(s['text'])
    
    if len(sentences_1) > 0:
        print_pass("Level 1 returned sentences")
    else:
        print_info("Level 1 may be empty if Level 0 got all matches")
    
    # Test Level 2 (Synonyms)
    print(f"\n{Colors.BOLD}--- Level 2: Synonyms ---{Colors.END}")
    sentences_2, k_off, s_off, exhausted_2 = retriever.fetch_level2_sentences(
        keyword_offset=0, synonym_offset=0, limit=5, used_texts=used_texts
    )
    print(f"   Found: {len(sentences_2)} sentences")
    print(f"   Keyword offset: {k_off}, Synonym offset: {s_off}, Exhausted: {exhausted_2}")
    for s in sentences_2[:3]:
        print(f"   - [{s['level']}] {s['text'][:60]}...")
        used_texts.add(s['text'])
    
    # Test Level 3 (Magical Words)
    print(f"\n{Colors.BOLD}--- Level 3: Keyword + Magical Words ---{Colors.END}")
    sentences_3, offset_3, exhausted_3 = retriever.fetch_level3_sentences(
        offset=0, limit=5, used_texts=used_texts
    )
    print(f"   Found: {len(sentences_3)} sentences")
    print(f"   Offset: {offset_3}, Exhausted: {exhausted_3}")
    for s in sentences_3[:3]:
        print(f"   - [{s['level']}] {s['text'][:60]}...")
    
    print(f"\n   Total unique sentences collected: {len(used_texts)}")
    
    return all_passed


# =============================================================================
# TEST 3: Session State & Deduplication
# =============================================================================

def test_session_deduplication():
    """Test that sessions track used sentences and don't repeat"""
    print_header("TEST 3: Session State & Deduplication")
    
    from services.keyword_extractor import extract_keywords
    from services.multi_level_retriever import get_next_batch
    
    keywords = ["grace", "freedom"]
    print_info(f"Testing with keywords: {keywords}")
    
    # Initial state
    session_state = {
        "current_level": 0,
        "level_offsets": {"0": 0, "1": 0, "2": [0, 0], "3": 0},
        "used_sentence_ids": []
    }
    
    all_sentences = []
    batch_num = 0
    all_passed = True
    
    # Get multiple batches
    while True:
        batch_num += 1
        print(f"\n{Colors.BOLD}--- Batch {batch_num} ---{Colors.END}")
        
        sentences, updated_state, level_used = get_next_batch(
            session_state=session_state,
            keywords=keywords,
            batch_size=10
        )
        
        print(f"   Level used: {level_used}")
        print(f"   Sentences returned: {len(sentences)}")
        print(f"   Current level after: {updated_state['current_level']}")
        print(f"   Total used: {len(updated_state['used_sentence_ids'])}")
        
        if not sentences:
            print_info("No more sentences available - all levels exhausted")
            break
        
        # Check for duplicates
        for s in sentences:
            text = s['text']
            if text in [x['text'] for x in all_sentences]:
                print_fail(f"Duplicate found: {text[:50]}...")
                all_passed = False
            all_sentences.append(s)
        
        session_state = updated_state
        
        if batch_num >= 5:  # Safety limit
            print_info("Reached batch limit (5)")
            break
    
    # Verify no duplicates in all collected sentences
    all_texts = [s['text'] for s in all_sentences]
    unique_texts = set(all_texts)
    
    if len(all_texts) == len(unique_texts):
        print_pass(f"No duplicates in {len(all_texts)} total sentences")
    else:
        print_fail(f"Found {len(all_texts) - len(unique_texts)} duplicates!")
        all_passed = False
    
    return all_passed


# =============================================================================
# TEST 4: API End-to-End Flow
# =============================================================================

def test_api_health():
    """Check if API is running"""
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=5)
        return resp.status_code == 200
    except:
        return False

def test_api_end_to_end():
    """Test full API flow: /ask → /continue → /continue"""
    print_header("TEST 4: API End-to-End Flow")
    
    if not test_api_health():
        print_fail("API is not running! Start it with: uvicorn main:app --port 8000")
        return False
    
    print_pass("API is healthy")
    
    all_passed = True
    
    # Step 1: Upload test corpus
    print(f"\n{Colors.BOLD}--- Step 1: Upload Test Corpus ---{Colors.END}")
    
    if TEST_CORPUS.exists():
        with open(TEST_CORPUS, 'rb') as f:
            files = {'file': ('test_corpus.txt', f, 'text/plain')}
            resp = requests.post(f"{API_BASE}/upload", files=files)
        
        if resp.status_code == 200:
            data = resp.json()
            print_pass(f"Uploaded: {data.get('total_sentences', 0)} sentences indexed")
        else:
            print_info(f"Upload response: {resp.status_code} - {resp.text[:100]}")
    else:
        print_info(f"Test corpus not found at {TEST_CORPUS}")
    
    # Step 2: Ask a question
    print(f"\n{Colors.BOLD}--- Step 2: POST /ask ---{Colors.END}")
    
    ask_payload = {
        "query": "How does grace unlock spiritual freedom?",
        "limit": 10
    }
    
    resp = requests.post(f"{API_BASE}/ask", json=ask_payload)
    
    if resp.status_code != 200:
        print_fail(f"Ask failed: {resp.status_code} - {resp.text[:100]}")
        return False
    
    ask_data = resp.json()
    session_id = ask_data.get("session_id")
    
    print_pass(f"Session created: {session_id[:20]}...")
    print(f"   Current level: {ask_data.get('current_level')}")
    print(f"   Max level: {ask_data.get('max_level')}")
    print(f"   Can continue: {ask_data.get('can_continue')}")
    print(f"   Sentences: {ask_data.get('sentences_retrieved')}")
    print(f"   Answer preview: {ask_data.get('answer', '')[:100]}...")
    
    # Check source sentences
    sources = ask_data.get("source_sentences", [])
    print(f"\n   Source sentences ({len(sources)}):")
    for i, s in enumerate(sources[:3]):
        print(f"   {i+1}. [L{s['level']}] {s['text'][:50]}...")
    
    # Step 3: Tell me more (multiple times)
    print(f"\n{Colors.BOLD}--- Step 3: POST /continue (Tell me more) ---{Colors.END}")
    
    continue_count = 0
    all_used_texts = set(s['text'] for s in sources)
    
    while ask_data.get("can_continue", False) and continue_count < 5:
        continue_count += 1
        print(f"\n   Continue #{continue_count}:")
        
        continue_payload = {
            "session_id": session_id,
            "limit": 10
        }
        
        resp = requests.post(f"{API_BASE}/continue", json=continue_payload)
        
        if resp.status_code == 400:
            print_info(f"   No more levels: {resp.json().get('detail', '')}")
            break
        
        if resp.status_code != 200:
            print_fail(f"   Continue failed: {resp.status_code}")
            all_passed = False
            break
        
        continue_data = resp.json()
        ask_data = continue_data  # Update for next loop
        
        print(f"   Level: {continue_data.get('current_level')}")
        print(f"   Can continue: {continue_data.get('can_continue')}")
        print(f"   Continue count: {continue_data.get('continue_count')}")
        print(f"   Sentences: {continue_data.get('sentences_retrieved')}")
        
        # Check for duplicates
        new_sources = continue_data.get("source_sentences", [])
        duplicates = [s for s in new_sources if s['text'] in all_used_texts]
        
        if duplicates:
            print_fail(f"   Found {len(duplicates)} duplicate sentences!")
            all_passed = False
        else:
            print_pass(f"   No duplicates, {len(new_sources)} new sentences")
        
        for s in new_sources:
            all_used_texts.add(s['text'])
    
    print(f"\n{Colors.BOLD}--- Summary ---{Colors.END}")
    print(f"   Total continue calls: {continue_count}")
    print(f"   Total unique sentences used: {len(all_used_texts)}")
    
    if all_passed:
        print_pass("End-to-end test completed successfully!")
    
    return all_passed


# =============================================================================
# TEST 5: Debug Endpoint (if available)
# =============================================================================

def test_debug_endpoint():
    """Test debug endpoint for detailed inspection"""
    print_header("TEST 5: Debug Endpoint")
    
    if not test_api_health():
        print_fail("API is not running!")
        return False
    
    # Try debug endpoint
    resp = requests.get(f"{API_BASE}/debug/keywords", params={"query": "How does grace unlock freedom?"})
    
    if resp.status_code == 200:
        data = resp.json()
        print_pass("Debug endpoint available")
        print(f"   Keywords: {data.get('keywords')}")
        print(f"   Combinations: {data.get('combinations')}")
        print(f"   Synonyms: {data.get('synonyms')}")
        return True
    else:
        print_info("Debug endpoint not available (optional)")
        return True  # Not a failure


# =============================================================================
# MAIN
# =============================================================================

def run_all_tests():
    """Run all tests"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     MULTI-LEVEL RETRIEVAL SYSTEM - TEST SUITE           ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"{Colors.END}")
    
    results = {}
    
    # Test 1: Keyword Extraction
    try:
        results["keyword_extraction"] = test_keyword_extraction()
    except Exception as e:
        print_fail(f"Test 1 error: {e}")
        results["keyword_extraction"] = False
    
    # Test 2: Level Retrieval
    try:
        results["level_retrieval"] = test_level_retrieval()
    except Exception as e:
        print_fail(f"Test 2 error: {e}")
        results["level_retrieval"] = False
    
    # Test 3: Session & Deduplication
    try:
        results["session_dedup"] = test_session_deduplication()
    except Exception as e:
        print_fail(f"Test 3 error: {e}")
        results["session_dedup"] = False
    
    # Test 4: API End-to-End
    try:
        results["api_e2e"] = test_api_end_to_end()
    except Exception as e:
        print_fail(f"Test 4 error: {e}")
        results["api_e2e"] = False
    
    # Test 5: Debug Endpoint (optional)
    try:
        results["debug_endpoint"] = test_debug_endpoint()
    except Exception as e:
        print_info(f"Test 5 skipped: {e}")
        results["debug_endpoint"] = True
    
    # Summary
    print_header("TEST RESULTS SUMMARY")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, passed_test in results.items():
        status = f"{Colors.GREEN}PASS{Colors.END}" if passed_test else f"{Colors.RED}FAIL{Colors.END}"
        print(f"   {name}: {status}")
    
    print(f"\n   {Colors.BOLD}Total: {passed}/{total} tests passed{Colors.END}")
    
    if passed == total:
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 ALL TESTS PASSED! 🎉{Colors.END}")
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}⚠️  Some tests failed. Check output above.{Colors.END}")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
