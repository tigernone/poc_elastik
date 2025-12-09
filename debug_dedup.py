#!/usr/bin/env python3
"""
Debug script để kiểm tra deduplication hoạt động
"""
import requests
import json
import sys

API_URL = "http://localhost:8000/ask"

def test_dedup():
    payload = {
        "query": "Zechariah and the baby Jesus",
        "limit": 15
    }
    
    print("=" * 100)
    print(f"Testing query: {payload['query']}")
    print("=" * 100)
    
    try:
        response = requests.post(API_URL, json=payload, timeout=120)
        
        if response.status_code != 200:
            print(f"❌ Error {response.status_code}:")
            print(response.text)
            return
        
        data = response.json()
        sources = data.get("source_sentences", [])
        
        print(f"\n✅ Got {len(sources)} source sentences\n")
        
        # Check for duplicates and near-duplicates
        seen = {}  # text -> index
        duplicates = []
        
        for i, sent in enumerate(sources):
            text = sent.get("text", "")
            level = sent.get("level", 0)
            score = sent.get("score", 0)
            source_type = sent.get("source_type", "Unknown")
            
            # Check if exact match
            if text in seen:
                duplicates.append({
                    "type": "EXACT",
                    "index": i,
                    "first_seen": seen[text],
                    "text": text[:100] + "..."
                })
                print(f"[{i}] ❌ EXACT DUPLICATE of index {seen[text]}")
            else:
                seen[text] = i
                print(f"[{i}] ✅ UNIQUE - {source_type} (Level {level}, Score {score:.2f})")
        
        print("\n" + "=" * 100)
        if duplicates:
            print(f"❌ FOUND {len(duplicates)} DUPLICATES:")
            for dup in duplicates:
                print(f"  Index {dup['index']}: {dup['type']} of index {dup['first_seen']}")
                print(f"    Text: {dup['text']}")
        else:
            print("✅ NO EXACT DUPLICATES FOUND")
        
        print("=" * 100)
        
        # Show sentences with "waked"/"wakened"
        print("\nSearching for 'waked' / 'wakened' variations:")
        for i, sent in enumerate(sources):
            text = sent.get("text", "").lower()
            if "waked" in text or "wakened" in text:
                full_text = sent.get("text", "")
                print(f"\n[{i}] {full_text[:150]}...")
        
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_dedup()
