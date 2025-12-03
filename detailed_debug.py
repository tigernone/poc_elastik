"""
More detailed debug to understand the flow.
"""

import sys
sys.path.insert(0, '/Users/minknguyen/Desktop/Working/POC/ai-vector-elastic-demo')

from services.multi_level_retriever import MultiLevelRetriever
from services.keyword_extractor import get_magical_words_for_level3

def detailed_debug():
    """Step through the logic manually."""
    
    keywords = ["heaven"]
    retriever = MultiLevelRetriever(keywords)
    magic_words = get_magical_words_for_level3()
    
    print("Magic words (first 10):", magic_words[:10])
    print("\n" + "=" * 80)
    
    used_texts = set()
    all_sentences = []
    
    # Manually step through first 3 magic words
    for i in range(min(3, len(magic_words))):
        magic = magic_words[i]
        keyword = "heaven"
        
        phrase1 = f"{keyword} {magic}"
        phrase2 = f"{magic} {keyword}"
        
        print(f"\nMagic Word #{i+1}: '{magic}'")
        print(f"Searching: '{phrase1}' or '{phrase2}'")
        print("=" * 80)
        
        # Search
        results1 = retriever._exact_phrase_search(phrase1, limit=500, exclude_texts=used_texts, slop=0)
        results2 = retriever._exact_phrase_search(phrase2, limit=500, exclude_texts=used_texts, slop=0)
        
        print(f"Found: {len(results1)} for '{phrase1}', {len(results2)} for '{phrase2}'")
        
        # Combine
        all_results = results1
        seen = {r["text"] for r in results1}
        for r in results2:
            if r["text"] not in seen:
                all_results.append(r)
                seen.add(r["text"])
        
        # Add to collection
        for r in all_results:
            if r["text"] not in used_texts:
                r["magic_word"] = magic
                all_sentences.append(r)
                used_texts.add(r["text"])
        
        print(f"Total added: {len(all_results)} unique sentences")
        print(f"Running total: {len(all_sentences)} sentences")
        
        # Show first 2 results
        for j, r in enumerate(all_results[:2], 1):
            text = r["text"][:80] + "..." if len(r["text"]) > 80 else r["text"]
            print(f"  {j}. {text}")
    
    print("\n" + "=" * 80)
    print(f"FINAL SUMMARY: {len(all_sentences)} total sentences from first 3 magic words")
    print("=" * 80)
    
    # Check order
    magic_order = [s.get("magic_word") for s in all_sentences]
    from collections import Counter
    counter = Counter(magic_order)
    
    for magic, count in counter.items():
        print(f"  '{magic}': {count} sentences")

if __name__ == "__main__":
    detailed_debug()
