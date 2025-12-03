"""
Debug script to check what Elasticsearch is actually returning.
"""

import sys
sys.path.insert(0, '/Users/minknguyen/Desktop/Working/POC/ai-vector-elastic-demo')

from services.multi_level_retriever import MultiLevelRetriever

def debug_search():
    """Debug what Elasticsearch returns."""
    
    keywords = ["heaven"]
    retriever = MultiLevelRetriever(keywords)
    
    print("Testing phrase search for 'heaven is' and 'is heaven':")
    print("=" * 80)
    
    # Test exact phrase search
    results1 = retriever._exact_phrase_search(
        phrase="heaven is",
        limit=50,
        exclude_texts=set(),
        slop=0
    )
    
    results2 = retriever._exact_phrase_search(
        phrase="is heaven",
        limit=50,
        exclude_texts=set(),
        slop=0
    )
    
    print(f"\nResults for 'heaven is': {len(results1)}")
    for i, r in enumerate(results1[:5], 1):
        text = r["text"][:100]
        print(f"{i}. {text}...")
    
    print(f"\nResults for 'is heaven': {len(results2)}")
    for i, r in enumerate(results2[:5], 1):
        text = r["text"][:100]
        print(f"{i}. {text}...")

if __name__ == "__main__":
    debug_search()
