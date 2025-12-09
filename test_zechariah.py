#!/usr/bin/env python3
"""
Test deduplication với câu hỏi: "Zechariah and the baby Jesus"
"""
import requests
import json

def test_deduplication():
    url = "http://localhost:8000/ask"
    payload = {
        "query": "Zechariah and the baby Jesus",
        "limit": 15
    }
    
    print("=" * 70)
    print("Testing: Zechariah and the baby Jesus")
    print("=" * 70)
    
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
    
    print(f"\n{'='*70}")
    if duplicates:
        print(f"❌ FOUND {len(duplicates)} DUPLICATES:")
        print(f"{'='*70}")
        for idx, dup_text in duplicates:
            print(f"\n[{idx}] {dup_text[:150]}...")
    else:
        print("✅ NO DUPLICATES FOUND - Deduplication working correctly!")
        print(f"{'='*70}")
    
    # Show first 10 results
    print(f"\nFirst 10 source sentences:")
    print(f"{'='*70}")
    for i, sent in enumerate(sources[:10]):
        source_type = sent.get("source_type", "Unknown")
        level = sent.get("level", 0)
        text = sent.get("text", "")
        print(f"\n[{i+1}] {source_type} (Level {level})")
        print(f"    {text[:200]}...")

if __name__ == "__main__":
    test_deduplication()
