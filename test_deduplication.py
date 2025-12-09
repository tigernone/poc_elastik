#!/usr/bin/env python3
"""
Test advanced deduplication functionality
"""
from services.deduplicator import (
    normalize_text,
    get_text_fingerprint,
    calculate_similarity,
    is_duplicate,
    deduplicate_sentences
)

print("=" * 60)
print("Testing Advanced Deduplication")
print("=" * 60)

# Test 1: Normalization
print("\n[Test 1] Text Normalization")
text1 = "Zechariah declares, 'came again, and waked me, as a man that is waked out of his sleep!'"
text2 = "Zechariah declares, 'came again, and wakened me, as a man that is wakened out of his sleep!'"
norm1 = normalize_text(text1)
norm2 = normalize_text(text2)
print(f"Original 1: {text1}")
print(f"Normalized: {norm1}")
print(f"\nOriginal 2: {text2}")
print(f"Normalized: {norm2}")

# Test 2: Fingerprinting
print("\n[Test 2] Text Fingerprinting (first 5 words)")
fp1 = get_text_fingerprint(text1)
fp2 = get_text_fingerprint(text2)
print(f"Fingerprint 1: {fp1}")
print(f"Fingerprint 2: {fp2}")
print(f"Match: {fp1 == fp2}")

# Test 3: Similarity Calculation
print("\n[Test 3] Similarity Calculation")
similarity = calculate_similarity(text1, text2)
print(f"Similarity: {similarity:.2%}")
print(f"Is duplicate (90% threshold): {similarity >= 0.90}")

# Test 4: is_duplicate function
print("\n[Test 4] is_duplicate() Function")
seen = {text1}
is_dup = is_duplicate(text2, seen, similarity_threshold=0.90)
print(f"Text 2 is duplicate of Text 1: {is_dup}")

# Test 5: Exact duplicates
print("\n[Test 5] Exact Duplicates")
text3 = "Zechariah declares, 'came again, and waked me!'"
text4 = "Zechariah declares, 'came again, and waked me!'"
is_dup_exact = is_duplicate(text4, {text3}, similarity_threshold=0.90)
print(f"Exact duplicate detected: {is_dup_exact}")

# Test 6: Different texts
print("\n[Test 6] Different Texts (should NOT be duplicates)")
text5 = "The Lord is leading to do his last work."
text6 = "In prophetic vision Zechariah was shown the day of final triumph."
similarity_diff = calculate_similarity(text5, text6)
is_dup_diff = is_duplicate(text6, {text5}, similarity_threshold=0.90)
print(f"Similarity: {similarity_diff:.2%}")
print(f"Is duplicate: {is_dup_diff}")

# Test 7: deduplicate_sentences function
print("\n[Test 7] deduplicate_sentences() Function")
sentences = [
    {"text": "Zechariah declares, 'came again, and waked me.'", "score": 1.0},
    {"text": "Zechariah declares, 'came again, and wakened me.'", "score": 0.9},  # Near duplicate
    {"text": "The Lord is leading to do his last work.", "score": 0.8},
    {"text": "Zechariah declares, came again, and waked me.", "score": 0.85},  # Near duplicate (no quotes)
    {"text": "In prophetic vision Zechariah was shown.", "score": 0.75},
]

print(f"Original: {len(sentences)} sentences")
unique = deduplicate_sentences(sentences, similarity_threshold=0.90)
print(f"After deduplication: {len(unique)} sentences")
print("\nUnique sentences:")
for i, sent in enumerate(unique, 1):
    print(f"  {i}. {sent['text'][:80]}...")

# Test 8: Case insensitive + punctuation
print("\n[Test 8] Case & Punctuation Variations")
variations = [
    "Zechariah declares, 'Came again, and waked me.'",  # Capital C
    "zechariah declares, 'came again, and waked me.'",  # lowercase z
    "Zechariah declares, came again, and waked me",     # no quotes, no period
    "Zechariah declares: 'came again, and waked me!'",  # colon, exclamation
]

base = {"Zechariah declares, 'came again, and waked me.'"}
print(f"Base text: {list(base)[0]}")
print("\nVariations:")
for var in variations:
    is_dup = is_duplicate(var, base, similarity_threshold=0.90)
    sim = calculate_similarity(var, list(base)[0])
    print(f"  [{sim:.2%}] {'DUP' if is_dup else 'NEW'}: {var}")

print("\n" + "=" * 60)
print("✅ Deduplication Tests Completed")
print("=" * 60)
print("\nKey Features:")
print("  ✓ Handles spelling variations (waked vs wakened)")
print("  ✓ Case insensitive matching")
print("  ✓ Punctuation normalization")
print("  ✓ 90% similarity threshold")
print("  ✓ Fast fingerprint matching for efficiency")
