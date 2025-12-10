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

# Initialize OpenAI client for keyword extraction (uses chat model))
if settings.DEEPSEEK_BASE_URL:
    client = OpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL
    )
else:
    client = OpenAI(api_key=settings.DEEPSEEK_API_KEY)

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
    prompt = f"""Extract ALL important keywords and phrases from the following text.

INSTRUCTIONS:
1. Extract ALL meaningful nouns, names, concepts, and phrases
2. Include proper names (Lord, Jesus, God, etc.)
3. Include compound phrases ("Master's table", "Holy Spirit", etc.)
4. DO NOT skip any significant words
5. Return as a JSON array

Examples:
- "Where is heaven?" → ["heaven"]
- "Lord give me faith" → ["Lord", "faith"]
- "What is the Holy Spirit?" → ["Holy Spirit"]
- "Woman at the Master's table" → ["woman", "Master's table"]

Text:
"{query}"

Return ONLY a JSON array, nothing else:"""
    
    try:
        print(f"[KeywordExtractor] Extracting keywords from: {query}")
        response = client.chat.completions.create(
            model=settings.CHAT_MODEL,
            messages=[
                {"role": "system", "content": "You are a precise keyword extractor. Extract ALL important keywords including proper names, compound phrases, and meaningful concepts. Return ONLY a JSON array."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,  # Zero temperature for maximum consistency
            max_tokens=300
        )
        
        content = response.choices[0].message.content.strip()
        print(f"[KeywordExtractor] LLM response: {content}")
        
        # Parse JSON - handle various formats
        # Try to find JSON array in response
        match = re.search(r'\[.*?\]', content, re.DOTALL)
        if match:
            keywords = json.loads(match.group())
            result = [k.lower().strip() for k in keywords if isinstance(k, str)]
            print(f"[KeywordExtractor] Extracted keywords: {result}")
            return result
        
        print(f"[KeywordExtractor] No JSON array found in response")
        return []
    except Exception as e:
        print(f"[KeywordExtractor] Error extracting keywords: {e}")
        # Fallback: simple word extraction, filter magic words
        words = query.lower().split()
        # Filter out magic words and short words
        filtered = [w for w in words if len(w) > 2 and w not in MAGIC_WORDS]
        fallback = filtered if filtered else [w for w in words if len(w) > 3]
        print(f"[KeywordExtractor] Using fallback extraction: {fallback}")
        return fallback


def filter_magic_words(keywords: List[str]) -> List[str]:
    """
    Filter out magic words from keyword list.
    Magic words are stopwords, common verbs, prepositions, etc.
    
    EXCEPTION: Preserve important proper names even if they're in magic_words list
    (e.g., Lord, God, Jesus, Christ, etc.)
    """
    # Important religious/proper names that should NEVER be filtered
    important_names = {
        'lord', 'god', 'jesus', 'christ', 'spirit', 'holy spirit',
        'father', 'son', 'holy', 'savior', 'messiah', 'yahweh', 'jehovah'
    }
    
    filtered = []
    for k in keywords:
        k_lower = k.lower()
        # Keep if it's an important name OR not in magic words
        if k_lower in important_names or k_lower not in MAGIC_WORDS:
            filtered.append(k)
    
    return filtered


def extract_keywords(query: str) -> List[str]:
    """
    Main function: Extract and filter keywords from query.
    Returns clean keywords ready for search.
    """
    raw_keywords = extract_keywords_raw(query)
    print(f"[KeywordExtractor] Raw keywords before filtering: {raw_keywords}")
    
    clean_keywords = filter_magic_words(raw_keywords)
    print(f"[KeywordExtractor] After magic word filtering: {clean_keywords}")
    
    # If all keywords were filtered, return original (excluding very common ones)
    if not clean_keywords and raw_keywords:
        very_common = {"is", "are", "was", "were", "the", "a", "an", "of", "to", "in"}
        clean_keywords = [k for k in raw_keywords if k not in very_common]
        print(f"[KeywordExtractor] All filtered, using fallback: {clean_keywords}")
    
    print(f"[KeywordExtractor] FINAL keywords returned: {clean_keywords}")
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
