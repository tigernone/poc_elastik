# services/deduplicator.py
"""
Advanced Deduplication Module
Handles near-duplicate detection with normalization and similarity checking
"""
import re
from typing import Set, List, Dict, Any
from difflib import SequenceMatcher


def normalize_text(text: str) -> str:
    """
    Normalize text for comparison by:
    - Converting to lowercase
    - Removing extra whitespace
    - Removing punctuation (keep only alphanumeric and spaces)
    - Stripping leading/trailing spaces
    """
    # Lowercase
    text = text.lower()
    # Remove punctuation except spaces
    text = re.sub(r'[^\w\s]', '', text)
    # Normalize whitespace
    text = ' '.join(text.split())
    return text.strip()


def get_text_fingerprint(text: str, first_n_words: int = 5) -> str:
    """
    Get fingerprint of text using first N words after normalization.
    This helps catch duplicates with minor variations at the end.
    """
    normalized = normalize_text(text)
    words = normalized.split()[:first_n_words]
    return ' '.join(words)


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity ratio between two texts (0.0 to 1.0).
    Uses SequenceMatcher for fuzzy matching.
    """
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    return SequenceMatcher(None, norm1, norm2).ratio()


def is_duplicate(
    text: str, 
    seen_texts: Set[str],
    similarity_threshold: float = 0.90,
    fingerprint_match: bool = True
) -> bool:
    """
    Check if text is a duplicate of any text in seen_texts.
    
    Uses two-stage approach:
    1. Fast fingerprint check (first 5 words)
    2. Full similarity check if needed
    
    Args:
        text: Text to check
        seen_texts: Set of previously seen texts
        similarity_threshold: Minimum similarity to consider duplicate (0.90 = 90%)
        fingerprint_match: Use fast fingerprint matching
        
    Returns:
        True if duplicate detected
    """
    if not text or not seen_texts:
        return False
    
    # Stage 1: Fast exact match
    if text in seen_texts:
        return True
    
    # Stage 2: Fast fingerprint match (first 5 words)
    if fingerprint_match:
        fingerprint = get_text_fingerprint(text)
        for seen in seen_texts:
            if get_text_fingerprint(seen) == fingerprint:
                return True
    
    # Stage 3: Full similarity check (slower, only for close matches)
    normalized = normalize_text(text)
    for seen in seen_texts:
        similarity = calculate_similarity(text, seen)
        if similarity >= similarity_threshold:
            return True
    
    return False


def deduplicate_sentences(
    sentences: List[Dict[str, Any]],
    existing_texts: Set[str] = None,
    similarity_threshold: float = 0.90,
    use_fingerprint: bool = True
) -> List[Dict[str, Any]]:
    """
    Remove duplicate sentences from a list, considering both exact and near-duplicates.
    
    Args:
        sentences: List of sentence dicts with 'text' field
        existing_texts: Set of texts already seen (to exclude)
        similarity_threshold: Similarity ratio to consider duplicate (0.90 = 90%)
        use_fingerprint: Use fingerprint matching for speed
        
    Returns:
        Deduplicated list of sentences
    """
    if not sentences:
        return []
    
    seen = set(existing_texts) if existing_texts else set()
    unique = []
    
    for sent in sentences:
        text = sent.get("text", "")
        if not text:
            continue
            
        # Check for duplicates using advanced matching
        if not is_duplicate(text, seen, similarity_threshold, use_fingerprint):
            seen.add(text)
            unique.append(sent)
    
    return unique


def get_unique_key(text: str) -> str:
    """
    Get a unique key for a text that captures its essence.
    Used for fast deduplication in sets.
    
    Combines:
    - Normalized text (for case/punctuation variations)
    - First 5 words (for longer texts with minor ending differences)
    """
    normalized = normalize_text(text)
    fingerprint = get_text_fingerprint(text)
    
    # For short texts (< 10 words), use full normalized text
    if len(normalized.split()) < 10:
        return normalized
    
    # For longer texts, use fingerprint to catch variations
    return fingerprint
