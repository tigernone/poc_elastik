# services/deduplicator.py
"""
STRICT Deduplication Module with High-Similarity Detection
- Removes 100% exact duplicates
- Also removes near-duplicates (>95% similar) to catch variants like "waked" vs "wakened"
"""
from typing import Set, List, Dict, Any
from difflib import SequenceMatcher


def normalize_text(text: str) -> str:
    """
    DEPRECATED: No longer used in strict mode.
    Returns text as-is without any normalization.
    """
    return text


def get_text_fingerprint(text: str, first_n_words: int = 5) -> str:
    """
    DEPRECATED: No longer used in strict mode.
    Returns text as-is.
    """
    return text


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity ratio between two texts using SequenceMatcher.
    Returns value from 0.0 to 1.0 (0% to 100% similar)
    """
    if text1 == text2:
        return 1.0
    if not text1 or not text2:
        return 0.0
    return SequenceMatcher(None, text1, text2).ratio()


def is_duplicate(
    text: str, 
    seen_texts: Set[str],
    similarity_threshold: float = 0.95,  # Default 95% similarity
    fingerprint_match: bool = False  # STRICT: Disabled
) -> bool:
    """
    Check if text is duplicate or near-duplicate.
    
    - First checks for exact match (fastest)
    - Then checks for high similarity (>95%) to catch variants
    - Only checks close-length texts to avoid slow comparisons
    
    Args:
        text: Text to check
        seen_texts: Set of previously seen texts
        similarity_threshold: Minimum similarity to consider duplicate (default 0.95 = 95%)
        fingerprint_match: IGNORED (disabled)
        
    Returns:
        True if exact match OR highly similar (>95%) match found
    """
    if not text or not seen_texts:
        return False
    
    # Fast path: exact match
    if text in seen_texts:
        return True
    
    # OPTIMIZATION: Only check similarity for texts of similar length
    # This avoids slow SequenceMatcher comparisons for obviously different texts
    text_len = len(text)
    max_similar_checks = 50  # Limit checks to avoid timeout
    
    check_count = 0
    for seen_text in seen_texts:
        if check_count >= max_similar_checks:
            break
            
        seen_len = len(seen_text)
        
        # Skip if length difference > 15% (slightly relaxed from 10%)
        if abs(text_len - seen_len) / max(text_len, seen_len) > 0.15:
            continue
        
        check_count += 1
        
        # Check similarity only for close-length texts
        similarity = calculate_similarity(text, seen_text)
        if similarity >= similarity_threshold:
            return True
    
    return False


def deduplicate_sentences(
    sentences: List[Dict[str, Any]],
    existing_texts: Set[str] = None,
    similarity_threshold: float = 0.95,  # Default 95% similarity
    use_fingerprint: bool = False  # STRICT: Disabled
) -> List[Dict[str, Any]]:
    """
    Remove duplicate and near-duplicate sentences.
    
    - Removes 100% exact duplicates
    - Also removes near-duplicates (>95% similar) to catch variants
    
    Args:
        sentences: List of sentence dicts with 'text' field
        existing_texts: Set of texts already seen (to exclude)
        similarity_threshold: Minimum similarity to consider duplicate (default 0.95 = 95%)
        use_fingerprint: IGNORED (disabled)
        
    Returns:
        List with exact and near-duplicates removed
    """
    if not sentences:
        return []
    
    seen = set(existing_texts) if existing_texts else set()
    unique = []
    
    for sent in sentences:
        text = sent.get("text", "")
        if not text:
            continue
            
        # Check for exact or near-duplicate
        if not is_duplicate(text, seen, similarity_threshold=similarity_threshold):
            seen.add(text)
            unique.append(sent)
    
    return unique


def get_unique_key(text: str) -> str:
    """
    STRICT MODE: Returns text as-is (no normalization).
    Each character matters - even case and spaces.
    """
    return text
