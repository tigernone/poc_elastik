#!/usr/bin/env python3
"""
Test script to verify logging is working correctly
"""
import requests
import json
import time

API_URL = "http://localhost:8000"

def test_logging():
    """Test API and check logs"""
    print("🔍 Testing logging functionality...\n")
    
    # Test 1: /ask endpoint
    print("1. Testing /ask endpoint...")
    response = requests.post(
        f"{API_URL}/ask",
        json={
            "query": "Lord give me the faith of the woman who asked for crumbs from the Master's table.",
            "limit": 5
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ /ask successful")
        print(f"   Keywords: {data.get('keywords', [])}")
        print(f"   Sentences: {len(data.get('source_sentences', []))}")
        print(f"   Session ID: {data.get('session_id')}")
        
        # Check logs
        time.sleep(1)
        print("\n📄 Checking logs/app.log for entries...")
        try:
            with open("logs/app.log", "r") as f:
                lines = f.readlines()
                recent_lines = lines[-10:]  # Last 10 lines
                for line in recent_lines:
                    if "[API /ask]" in line:
                        print(f"   {line.strip()}")
        except FileNotFoundError:
            print("   ⚠️  logs/app.log not found")
    else:
        print(f"❌ /ask failed: {response.status_code}")
        print(f"   {response.text}")
    
    print("\n✅ Logging test complete!")
    print("📁 Check these log files:")
    print("   - logs/app.log (application logs)")
    print("   - logs/fastapi.log (FastAPI server logs)")

if __name__ == "__main__":
    test_logging()
