# services/keyword_extractor.py
"""
Keyword Extractor - Step 1 of Multi-Level Retrieval
1. Extract keywords from user query using LLM
2. Filter out magic words (stopwords, common verbs, etc.)
3. Generate keyword combinations for different levels
"""
import os
import json
import re
from typing import List, Set, Tuple
from openai import OpenAI
from pathlib import Path
from config import settings

# Initialize OpenAI client for keyword extraction (uses chat model)
if settings.OPENAI_BASE_URL:
    client = OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL
    )
else:
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Load magic words from file
MAGIC_WORDS_PATH = Path(__file__).parent.parent / "magic_words.txt"


def load_magic_words() -> Set[str]:
    """Load magic words from file and return as lowercase set"""
    magic_words = set()
    try:
        if MAGIC_WORDS_PATH.exists():
            with open(MAGIC_WORDS_PATH, "r", encoding="utf-8") as f:
                content = f.read()
                # Split by comma and clean
                words = [w.strip().lower() for w in content.split(",")]
                magic_words = set(w for w in words if w)
    except Exception as e:
        print(f"Warning: Could not load magic_words.txt: {e}")
    return magic_words


# Cache magic words at module load
MAGIC_WORDS = load_magic_words()


def extract_keywords_raw(query: str) -> List[str]:
    """
    Extract keywords from query using LLM.
    Returns raw keywords before filtering.
    """
    prompt = f"""Extract ONLY meaningful keywords from this question.

RULES:
1. Extract ONLY nouns and key concepts (theological/spiritual terms)
2. DO NOT include:
   - Question words: where, what, when, who, why, how, which
   - Inferred/implied words like "location", "place", "reason", "time", "person"
   - Common verbs: is, are, was, were, be, do, does, did, have, has
   - Prepositions: in, on, at, to, for, with, about, between
   - Articles: the, a, an
3. Return ONLY the actual meaningful words that appear or are directly related to the topic

Question: "{query}"

Example 1: "Where is heaven?" → ["heaven"]
Example 2: "What is salvation?" → ["salvation"]  
Example 3: "Why did Jesus die on the cross?" → ["Jesus", "cross", "die"]
Example 4: "Who is the Holy Spirit?" → ["Holy Spirit"]

Return as JSON array only, no explanation.
"""
    
    try:
        response = client.chat.completions.create(
            model=settings.CHAT_MODEL,  # Use configured chat model (deepseek-chat or gpt-4o-mini)
            messages=[
                {"role": "system", "content": "You are a keyword extractor. Return only JSON array."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )
        
        content = response.choices[0].message.content.strip()
        
        # Parse JSON - handle various formats
        # Try to find JSON array in response
        match = re.search(r'\[.*?\]', content, re.DOTALL)
        if match:
            keywords = json.loads(match.group())
            return [k.lower().strip() for k in keywords if isinstance(k, str)]
        
        return []
    except Exception as e:
        print(f"Error extracting keywords: {e}")
        # Fallback: simple word extraction, filter magic words
        words = query.lower().split()
        # Filter out magic words and short words
        filtered = [w for w in words if len(w) > 2 and w not in MAGIC_WORDS]
        return filtered if filtered else [w for w in words if len(w) > 3]


def filter_magic_words(keywords: List[str]) -> List[str]:
    """
    Filter out magic words from keyword list.
    Magic words are stopwords, common verbs, prepositions, etc.
    """
    return [k for k in keywords if k.lower() not in MAGIC_WORDS]


def extract_keywords(query: str) -> List[str]:
    """
    Main function: Extract and filter keywords from query.
    Returns clean keywords ready for search.
    """
    raw_keywords = extract_keywords_raw(query)
    clean_keywords = filter_magic_words(raw_keywords)
    
    # If all keywords were filtered, return original (excluding very common ones)
    if not clean_keywords and raw_keywords:
        very_common = {"is", "are", "was", "were", "the", "a", "an", "of", "to", "in"}
        clean_keywords = [k for k in raw_keywords if k not in very_common]
    
    return clean_keywords


def generate_keyword_combinations(keywords: List[str]) -> List[Tuple[str, ...]]:
    """
    Generate keyword combinations for Level 0 search.
    Returns tuples from most specific (all keywords) to least (single).
    
    Example: ["grace", "freedom", "salvation"] ->
    [
        ("grace", "freedom", "salvation"),  # 3 keywords
        ("grace", "freedom"),               # 2 keywords
        ("grace", "salvation"),
        ("freedom", "salvation"),
        ("grace",),                         # single
        ("freedom",),
        ("salvation",)
    ]
    """
    from itertools import combinations
    
    result = []
    n = len(keywords)
    
    # Start from full combination down to single
    for size in range(n, 0, -1):
        for combo in combinations(keywords, size):
            result.append(combo)
    
    return result


def generate_synonyms(keyword: str) -> List[str]:
    """
    Generate synonyms for a keyword using LLM.
    Used for Level 2 search.
    """
    prompt = f"""Give 2-3 synonyms or related theological terms for the word "{keyword}".
Return as JSON array only. Focus on spiritual/theological context.

Example for "grace": ["mercy", "blessing", "favor"]
"""
    
    try:
        response = client.chat.completions.create(
            model=settings.CHAT_MODEL,  # Use configured chat model
            messages=[
                {"role": "system", "content": "You are a thesaurus. Return only JSON array."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=100
        )
        
        content = response.choices[0].message.content.strip()
        match = re.search(r'\[.*?\]', content, re.DOTALL)
        if match:
            synonyms = json.loads(match.group())
            return [s.lower().strip() for s in synonyms if isinstance(s, str)]
        
        return []
    except Exception as e:
        print(f"Error generating synonyms for {keyword}: {e}")
        return []


def get_magical_words_for_level3() -> List[str]:
    """
    Get magic words in PRIORITY ORDER from magic_words.txt file.
    
    The order in magic_words.txt determines search priority:
    - "is" comes first → "heaven is" searched before "heaven are"
    - "are" comes second → "heaven are" searched after "heaven is"
    - etc.
    
    This ensures:
    1. First exhaust all "keyword + is" matches
    2. Then all "keyword + are" matches
    3. And so on...
    """
    try:
        if MAGIC_WORDS_PATH.exists():
            with open(MAGIC_WORDS_PATH, "r", encoding="utf-8") as f:
                content = f.read()
                # Split by comma and preserve ORDER from file
                words = [w.strip() for w in content.split(",")]
                # Return non-empty words in original order
                return [w for w in words if w]
    except Exception as e:
        print(f"Warning: Could not load magic_words.txt: {e}")
    
    # Fallback to default list if file not found
    return ["is", "are", "was", "were", "be", "been", "being"]


def generate_keyword_magical_pairs(keywords: List[str]) -> List[Tuple[str, str]]:
    """
    Generate keyword + magical word pairs for Level 3 search.
    E.g., [("grace", "is"), ("grace", "brings"), ("freedom", "is"), ...]
    """
    magical_words = get_magical_words_for_level3()
    pairs = []
    
    for keyword in keywords:
        for magic in magical_words:
            pairs.append((keyword, magic))
    
    return pairs
