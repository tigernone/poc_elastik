#!/usr/bin/env python3
"""
Quick test to validate multi-level retrieval logic matches client requirements:

Level 0: keyword combinations (multi keywords only)
Level 1: keyword + magic words (strict phrase, slop=0)
Level 2: synonym combinations 
Level 3: synonym + magic words (strict phrase, slop=0)
Level 4: semantic vector search
"""
import sys
from services.multi_level_retriever import get_next_batch

def print_header(text):
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}")

def test_single_keyword():
    """Test with single keyword - should skip Level 0, start at Level 1"""
    print_header("TEST 1: Single Keyword (grace)")
    
    keywords = ["grace"]
    session_state = {
        "current_level": 0,
        "level_offsets": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0},
        "used_sentence_ids": []
    }
    
    # Get first batch
    sentences, updated_state, level_used = get_next_batch(
        session_state=session_state,
        keywords=keywords,
        batch_size=5
    )
    
    print(f"\n✓ Returned {len(sentences)} sentences")
    print(f"✓ Level used: {level_used}")
    print(f"✓ Current level after: {updated_state['current_level']}")
    print(f"✓ Should be Level 1 (keyword + magic words)")
    
    if len(sentences) > 0:
        print(f"\nFirst few results:")
        for i, s in enumerate(sentences[:3], 1):
            magic = s.get('magic_word', 'N/A')
            match_type = s.get('match_type', 'N/A')
            print(f"  {i}. Magic: '{magic}' | Type: {match_type}")
            print(f"     Text: {s['text'][:100]}...")
    
    return level_used == 1  # Should start at level 1 for single keyword

def test_multiple_keywords():
    """Test with multiple keywords - should start at Level 0"""
    print_header("TEST 2: Multiple Keywords (grace, freedom)")
    
    keywords = ["grace", "freedom"]
    session_state = {
        "current_level": 0,
        "level_offsets": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0},
        "used_sentence_ids": []
    }
    
    # Get first batch
    sentences, updated_state, level_used = get_next_batch(
        session_state=session_state,
        keywords=keywords,
        batch_size=5
    )
    
    print(f"\n✓ Returned {len(sentences)} sentences")
    print(f"✓ Level used: {level_used}")
    print(f"✓ Current level after: {updated_state['current_level']}")
    print(f"✓ Should be Level 0 (keyword combinations)")
    
    if len(sentences) > 0:
        print(f"\nFirst few results:")
        for i, s in enumerate(sentences[:3], 1):
            print(f"  {i}. Level: {s.get('level', 'N/A')}")
            print(f"     Text: {s['text'][:100]}...")
    
    return level_used == 0  # Should start at level 0 for multi keywords

def test_level_progression():
    """Test that levels progress correctly: 0 -> 1 -> 2 -> 3 -> 4"""
    print_header("TEST 3: Level Progression (Exhaustive)")
    
    keywords = ["grace", "freedom"]
    session_state = {
        "current_level": 0,
        "level_offsets": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0},
        "used_sentence_ids": []
    }
    
    levels_seen = []
    max_batches = 100  # Allow many batches to see full progression
    
    print(f"\n  Fetching batches until we see all levels (max {max_batches} batches)...")
    
    for batch_num in range(1, max_batches + 1):
        sentences, session_state, level_used = get_next_batch(
            session_state=session_state,
            keywords=keywords,
            batch_size=5  # Reasonable batch size
        )
        
        if not sentences:
            print(f"\n  Batch {batch_num}: No more results (all levels exhausted)")
            break
        
        # Track level changes
        if not levels_seen or levels_seen[-1] != level_used:
            levels_seen.append(level_used)
            print(f"\n  ▶ Level {level_used} started at batch {batch_num}")
            
            # Show sample
            if sentences:
                s = sentences[0]
                magic = s.get('magic_word', '')
                syn = s.get('synonym_used', '')
                combo = s.get('synonym_combo', '')
                
                detail = ""
                if magic:
                    detail = f"magic='{magic}'"
                if syn:
                    detail += f" syn='{syn}'"
                if combo:
                    detail += f" combo={combo}"
                
                print(f"    Sample: {s['text'][:80]}... [{detail}]")
        
        # Stop if we've seen all 5 levels
        if len(set(levels_seen)) == 5:
            print(f"\n  ✅ All 5 levels observed! Stopping at batch {batch_num}")
            break
    
    print(f"\n✓ Levels seen: {' -> '.join(map(str, levels_seen))}")
    print(f"✓ Unique levels: {sorted(set(levels_seen))}")
    
    # Success if we see levels in order (may repeat, but order should be ascending)
    is_ordered = all(levels_seen[i] <= levels_seen[i+1] for i in range(len(levels_seen)-1))
    has_level_0 = 0 in levels_seen
    has_level_1 = 1 in levels_seen
    
    print(f"\n  Validation:")
    print(f"  - Levels in ascending order: {'✓' if is_ordered else '✗'}")
    print(f"  - Started with Level 0 (multi-keyword): {'✓' if has_level_0 else '✗'}")
    print(f"  - Progressed to Level 1 (magic): {'✓' if has_level_1 else '✗'}")
    
    return is_ordered and has_level_0 and has_level_1

def test_level_descriptions():
    """Print what each level should do"""
    print_header("LEVEL DEFINITIONS (Client Requirements)")
    
    print("""
    Level 0: Keyword combinations (multiple keywords only)
             - Combines all keywords: "grace freedom", "grace", "freedom"
             - Uses multi_match with require_all_words=True
             
    Level 1: Keyword + Magic words (strict phrase, slop=0)
             - Pairs each keyword with magic words (is, was, are, etc.)
             - Strict phrase matching: "grace is", "freedom was"
             - slop=0 means exact consecutive order
             
    Level 2: Synonym combinations
             - Generate synonyms for each keyword
             - Combine synonym terms like Level 0
             - Example: "mercy", "liberty", "mercy liberty"
             
    Level 3: Synonym + Magic words (strict phrase, slop=0)
             - Pairs synonym terms with magic words
             - Strict phrase matching: "mercy is", "liberty was"
             - slop=0 means exact consecutive order
             
    Level 4: Semantic vector search (fallback)
             - Full embedding similarity search
             - No strict matching requirements
             - Broadest recall
    """)

if __name__ == "__main__":
    print("\n" + "="*70)
    print("  MULTI-LEVEL RETRIEVER VALIDATION TEST")
    print("  Testing against client requirements")
    print("="*70)
    
    # Show level definitions
    test_level_descriptions()
    
    # Run tests
    results = []
    
    try:
        results.append(("Single keyword routing", test_single_keyword()))
    except Exception as e:
        print(f"\n❌ ERROR in single keyword test: {e}")
        results.append(("Single keyword routing", False))
    
    try:
        results.append(("Multiple keyword routing", test_multiple_keywords()))
    except Exception as e:
        print(f"\n❌ ERROR in multiple keyword test: {e}")
        results.append(("Multiple keyword routing", False))
    
    try:
        results.append(("Level progression", test_level_progression()))
    except Exception as e:
        print(f"\n❌ ERROR in progression test: {e}")
        results.append(("Level progression", False))
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {test_name}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n  🎉 All tests passed! Logic matches client requirements.")
        sys.exit(0)
    else:
        print("\n  ⚠️  Some tests failed. Review logic above.")
        sys.exit(1)
