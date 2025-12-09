#!/usr/bin/env python3
"""
Simple live test harness for the deployed /ask endpoint.
Sends a list of queries and validates the presence of `biblical_parallels` and
some expected substrings for the "living water" query.

Usage:
    python3 tests/run_live_checks.py

Adjust `API_URL` if your API is hosted at a different host/port.
"""
import json
import sys
import time
from typing import List, Dict

import requests

API_URL = "http://18.189.170.169:8000/ask"  # live API
HEADERS = {"Content-Type": "application/json"}
TIMEOUT = 30

QUERIES = [
    {
        "name": "living_water",
        "payload": {"query": "What is the meaning of living water in the Bible?", "limit": 10},
        "expect_keys": ["biblical_parallels", "source_sentences", "answer"],
        "expect_in_parallels": ["John 4", "John 7", "Ezekiel", "living water", "Holy Spirit"],
    },
    {"name": "parable", "payload": {"query": "parable", "limit": 8}, "expect_keys": ["biblical_parallels", "source_sentences", "answer"]},
    {"name": "grace", "payload": {"query": "grace", "limit": 8}, "expect_keys": ["biblical_parallels", "source_sentences", "answer"]},
    {"name": "joseph", "payload": {"query": "forgiveness and redemption in the story of Joseph", "limit": 10}, "expect_keys": ["biblical_parallels", "source_sentences", "answer"]},
    {"name": "covenant_examples", "payload": {"query": "examples of covenant in the Old Testament", "limit": 10}, "expect_keys": ["biblical_parallels", "source_sentences", "answer"]},
    {"name": "what_is_love", "payload": {"query": "What is love?", "limit": 6}, "expect_keys": ["biblical_parallels", "source_sentences", "answer"]},
]


def send_request(payload: Dict) -> Dict:
    try:
        r = requests.post(API_URL, headers=HEADERS, data=json.dumps(payload), timeout=TIMEOUT)
    except Exception as e:
        return {"error": f"Request failed: {e}"}
    try:
        return {"status_code": r.status_code, "json": r.json()}
    except Exception:
        return {"status_code": r.status_code, "text": r.text}


def check_response(res_obj: Dict, test_def: Dict) -> Dict:
    result = {"ok": False, "reasons": []}
    if "error" in res_obj:
        result["reasons"].append(res_obj["error"])
        return result
    status = res_obj.get("status_code", 0)
    if status != 200:
        result["reasons"].append(f"Status code {status}")
        # include body text for diagnostics
        if "text" in res_obj:
            result["reasons"].append(res_obj["text"])
        return result

    body = res_obj.get("json", {})
    # Expect keys
    for k in test_def.get("expect_keys", []):
        if k not in body:
            result["reasons"].append(f"Missing key: {k}")

    # For living_water, check presence of expected tokens in biblical_parallels
    if test_def["name"] == "living_water" and "biblical_parallels" in body:
        parallels = body.get("biblical_parallels", {})
        flat = json.dumps(parallels).lower()
        for token in test_def.get("expect_in_parallels", []):
            if token.lower() not in flat:
                result["reasons"].append(f"Expected token not found in biblical_parallels: {token}")

    # Check source_sentences is non-empty
    ss = body.get("source_sentences")
    if not ss or not isinstance(ss, list) or len(ss) == 0:
        result["reasons"].append("source_sentences is empty or missing")

    if not result["reasons"]:
        result["ok"] = True
    return result


def main():
    summary = {}
    for t in QUERIES:
        print(f"\n--- Testing: {t['name']} ---")
        print(f"Payload: {t['payload']}")
        res = send_request(t["payload"])
        chk = check_response(res, t)
        print("Result:", "PASS" if chk["ok"] else "FAIL")
        if chk["reasons"]:
            print("Reasons:")
            for r in chk["reasons"]:
                print(" -", r)
        # Pretty-print some useful fields when available
        if "json" in res and isinstance(res["json"], dict):
            body = res["json"]
            # print short answer
            ans = body.get("answer")
            if ans:
                print("Answer (snippet):", (ans[:400] + '...') if len(ans) > 400 else ans)
            # print biblical_parallels snippet
            if "biblical_parallels" in body:
                print("Biblical Parallels:", json.dumps(body["biblical_parallels"], ensure_ascii=False)[:700])
        summary[t["name"]] = chk
        # small delay to avoid rate limits
        time.sleep(1)

    print("\n=== SUMMARY ===")
    for k, v in summary.items():
        print(f"{k}: {'PASS' if v['ok'] else 'FAIL'}")
        if not v["ok"]:
            for r in v["reasons"]:
                print("   -", r)

    # Exit code non-zero if any fail
    any_fail = any(not v["ok"] for v in summary.values())
    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
