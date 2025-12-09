#!/usr/bin/env python3
"""
Test deduplication với nhiều queries khác nhau
"""
import requests
import json
import time

def test_query(query, limit=15):
    url = "http://localhost:8000/ask"
    payload = {
        "query": query,
        "limit": limit
    }
    
    print("=" * 80)
    print(f"Testing: {query}")
    print("=" * 80)
    
    try:
        response = requests.post(url, json=payload, timeout=120)
        
        if response.status_code != 200:
            print(f"❌ Error: {response.status_code}")
            print(response.text)
            return
        
        data = response.json()
        sources = data.get("source_sentences", [])
        
        print(f"\n✅ API Response received")
        print(f"Total source sentences: {len(sources)}")
        
        # Check for duplicates
        seen = set()
        duplicates = []
        
        for i, sent in enumerate(sources):
            text = sent.get("text", "")
            if text in seen:
                duplicates.append((i+1, text))
            else:
                seen.add(text)
        
        print(f"\n{'='*80}")
        if duplicates:
            print(f"❌ FOUND {len(duplicates)} DUPLICATES:")
            print(f"{'='*80}")
            for idx, dup_text in duplicates:
                print(f"\n[{idx}] {dup_text[:150]}...")
        else:
            print("✅ NO DUPLICATES FOUND - Deduplication working correctly!")
        
        # Count by source type
        source_types = {}
        for sent in sources:
            source_type = sent.get("source_type", "Unknown")
            source_types[source_type] = source_types.get(source_type, 0) + 1
        
        print(f"\n{'='*80}")
        print("Source breakdown:")
        for st, count in source_types.items():
            print(f"  {st}: {count}")
        
        print(f"{'='*80}\n")
        
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    # Test multiple queries
    queries = [
        "Zechariah and the baby Jesus",
        "heaven is",
        "Moses and the promised land",
    ]
    
    for query in queries:
        test_query(query)
        time.sleep(2)  # Wait between queries
