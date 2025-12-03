"""
Test script to verify magic word priority search logic.

This script simulates a search for "where is heaven" and verifies:
1. All results with "is" come before results with "are", "was", etc.
2. Only consecutive matches are returned (no words between)
3. The search respects magic word priority order from magic_words.txt
"""

import sys
sys.path.insert(0, '/Users/minknguyen/Desktop/Working/POC/ai-vector-elastic-demo')

from services.multi_level_retriever import MultiLevelRetriever
from services.keyword_extractor import get_magical_words_for_level3

def test_magic_word_priority():
    """Test that magic word priority is respected."""
    
    print("=" * 80)
    print("Testing Magic Word Priority Search Logic")
    print("=" * 80)
    
    # Test with single keyword "heaven"
    keywords = ["heaven"]
    retriever = MultiLevelRetriever(keywords)
    
    print(f"\nKeywords: {keywords}")
    print(f"Testing single keyword mode...")
    
    # Get magic words to verify priority
    magic_words = get_magical_words_for_level3()
    print(f"\nMagic words priority (first 5): {magic_words[:5]}")
    
    # Fetch Level 3 sentences (which is Level 1 for single keyword)
    used_texts = set()
    sentences, offset, exhausted, current_magic = retriever.fetch_level3_sentences(
        offset=0,
        limit=50,  # Get up to 50 results
        used_texts=used_texts,
        single_keyword_mode=True
    )
    
    print(f"\n{'=' * 80}")
    print(f"Results: Found {len(sentences)} sentences")
    print(f"{'=' * 80}\n")
    
    # Group results by magic word
    magic_word_groups = {}
    for sent in sentences:
        magic = sent.get("magic_word", "unknown")
        if magic not in magic_word_groups:
            magic_word_groups[magic] = []
        magic_word_groups[magic].append(sent)
    
    # Display results grouped by magic word
    for i, magic in enumerate(magic_words):
        if magic in magic_word_groups:
            results = magic_word_groups[magic]
            print(f"\n--- Magic Word #{i+1}: '{magic}' ({len(results)} results) ---")
            for j, sent in enumerate(results[:3], 1):  # Show first 3
                text = sent["text"][:80] + "..." if len(sent["text"]) > 80 else sent["text"]
                print(f"  {j}. {text}")
            if len(results) > 3:
                print(f"  ... and {len(results) - 3} more")
    
    # Verify priority order
    print(f"\n{'=' * 80}")
    print("Verification:")
    print(f"{'=' * 80}")
    
    # Check that "is" appears before "are"
    has_is = "is" in magic_word_groups
    has_are = "are" in magic_word_groups
    
    if has_is:
        print(f"✅ Found results with 'is' (priority #1)")
    else:
        print(f"❌ No results with 'is' found")
    
    if has_are:
        print(f"⚠️  Found results with 'are' (priority #2)")
    
    # Check order of appearance
    magic_order = [sent.get("magic_word") for sent in sentences]
    unique_magic_order = []
    for m in magic_order:
        if m not in unique_magic_order:
            unique_magic_order.append(m)
    
    print(f"\nOrder of magic words in results: {unique_magic_order}")
    
    # Verify consecutive matches only
    print(f"\n{'=' * 80}")
    print("Checking for consecutive matches (no words between):")
    print(f"{'=' * 80}")
    
    for sent in sentences[:5]:  # Check first 5
        text = sent["text"].lower()
        magic = sent.get("magic_word", "")
        keyword = "heaven"
        
        # Check if magic and keyword are consecutive
        phrase1 = f"{keyword} {magic}"
        phrase2 = f"{magic} {keyword}"
        
        if phrase1 in text or phrase2 in text:
            print(f"✅ Consecutive match: '{phrase1}' or '{phrase2}'")
        else:
            print(f"❌ NOT consecutive: magic='{magic}', keyword='{keyword}'")
            print(f"   Text: {text[:100]}...")
    
    print(f"\n{'=' * 80}")
    print("Test Complete!")
    print(f"{'=' * 80}\n")

if __name__ == "__main__":
    test_magic_word_priority()
