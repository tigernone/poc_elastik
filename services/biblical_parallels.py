"""Biblical parallels extractor and retrieval helpers."""
import json
import logging
import re
from typing import Dict, List, Optional, Set, Tuple

from openai import OpenAI

from config import settings
from services.deduplicator import deduplicate_sentences, is_duplicate
from services.multi_level_retriever import MultiLevelRetriever, get_pure_semantic_search

logger = logging.getLogger(__name__)

if settings.DEEPSEEK_BASE_URL:
    client = OpenAI(api_key=settings.DEEPSEEK_API_KEY, base_url=settings.DEEPSEEK_BASE_URL)
else:
    client = OpenAI(api_key=settings.DEEPSEEK_API_KEY)

# Broad theological terms to exclude when they are not tied to a specific passage/character
GENERIC_THEOLOGY_TERMS = {
    "grace",
    "faith",
    "love",
    "salvation",
    "redemption",
    "righteousness",
    "justification",
    "sanctification",
    "prayer",
    "repentance",
    "atonement",
    "sin",
    "forgiveness",
}


def _safe_parse_json(content: str) -> Dict[str, List[str]]:
    """Parse JSON content from LLM response robustly."""
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _filter_generic(items: List[str]) -> List[str]:
    filtered: List[str] = []
    for item in items or []:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned:
            continue
        lower = cleaned.lower()
        if any(term in lower for term in GENERIC_THEOLOGY_TERMS):
            continue
        filtered.append(cleaned)
    return filtered


def analyze_biblical_parallels(query: str) -> Dict[str, List[str]]:
    """Call LLM to extract concise biblical parallels before Level 0."""
    prompt = f"""You are a precise Biblical parallels analyst. For the user input, extract concise, context-accurate items in four sections.

Rules:
- Return ONLY JSON with keys: stories_characters, scripture_references, biblical_metaphors, keywords.
- Each item must be specific to the context of "{query}" and anchored in Scripture.
- Keep items concise (3-10 words). Avoid bullet text or commentary.
- Exclude generic theological words that are not tied to specific passages or characters (grace, faith, love, salvation, redemption, righteousness, justification, sanctification, prayer, repentance, atonement, sin, forgiveness).
- Prefer explicit narrative titles, named characters, clear references (Book Chapter:Verse), and well-known biblical metaphors or symbols.

Output JSON example format:
{{
  "stories_characters": ["David and Goliath", "Woman at the well"],
  "scripture_references": ["Genesis 12:1-9", "John 4:4-26"],
  "biblical_metaphors": ["salt of the earth", "vine and branches"],
  "keywords": ["covenant promise", "living water"]
}}
"""

    try:
        response = client.chat.completions.create(
            model=settings.CHAT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You extract specific biblical parallels as strict JSON. Be concise and avoid generic theology terms.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=400,
        )
        raw_content = response.choices[0].message.content.strip()
        parsed = _safe_parse_json(raw_content)
    except Exception as exc:
        logger.warning(f"[BiblicalParallels] LLM extraction failed: {exc}")
        parsed = {}

    result: Dict[str, List[str]] = {
        "stories_characters": _filter_generic(parsed.get("stories_characters", [])),
        "scripture_references": _filter_generic(parsed.get("scripture_references", [])),
        "biblical_metaphors": _filter_generic(parsed.get("biblical_metaphors", [])),
        "keywords": _filter_generic(parsed.get("keywords", [])),
    }
    return result


def _tag_sentence(sent: Dict[str, str], source_type: str, is_primary: bool = True) -> Dict[str, str]:
    sent["source"] = "biblical_parallels"
    sent["source_type"] = source_type
    sent["is_primary_source"] = is_primary
    return sent


def gather_biblical_parallels_sentences(
    parallels: Dict[str, List[str]],
    existing_texts: Optional[Set[str]] = None,
    base_query: Optional[str] = None,
) -> Tuple[List[Dict[str, str]], Set[str]]:
    """
    Fetch supporting sentences for the biblical parallels layer before Level 0.

    - Stories/Characters: vector search to ~5 sentences
    - Scripture references: vector search to ~3 sentences
    - Biblical metaphors: blended vector search to ~5 sentences
    - Keywords: keyword-guided search, ~2 per keyword (capped)
    """
    collected: List[Dict[str, str]] = []
    used: Set[str] = set(existing_texts) if existing_texts else set()

    stories = parallels.get("stories_characters", [])[:4]
    scripture_refs = parallels.get("scripture_references", [])[:4]
    metaphors = parallels.get("biblical_metaphors", [])[:5]
    keywords = parallels.get("keywords", [])[:4]

    retriever = MultiLevelRetriever(keywords or ([] if base_query is None else base_query.split()))

    def add_vector_items(items: List[str], total_limit: int, label: str):
        for item in items:
            if len([s for s in collected if s.get("source_type") == label]) >= total_limit:
                break
            remaining = total_limit - len([s for s in collected if s.get("source_type") == label])
            hits = get_pure_semantic_search(item, limit=remaining, exclude_texts=used)
            for hit in hits:
                if is_duplicate(hit["text"], used, similarity_threshold=0.95):
                    continue
                collected.append(_tag_sentence(hit, label, is_primary=True))
                used.add(hit["text"])

    def add_keyword_items(items: List[str], per_keyword: int, label: str):
        for item in items:
            count_for_item = 0
            # Use keyword-focused search with vector scoring
            hits = retriever._text_search(
                query_text=item,
                limit=per_keyword * 2,
                exclude_texts=used,
                use_vector=True,
                match_type="match",
                require_all_words=True,
            )
            for hit in hits:
                if is_duplicate(hit["text"], used, similarity_threshold=0.95):
                    continue
                collected.append(_tag_sentence(hit, label, is_primary=False))
                used.add(hit["text"])
                count_for_item += 1
                if count_for_item >= per_keyword:
                    break

    # Vector-heavy pulls
    add_vector_items(stories, total_limit=5, label="Biblical Stories/Characters")
    add_vector_items(scripture_refs, total_limit=3, label="Scripture References")
    add_vector_items(metaphors, total_limit=5, label="Biblical Metaphors")

    # Keyword-focused pulls (capped to avoid explosion)
    add_keyword_items(keywords, per_keyword=2, label="Biblical Keywords")

    # Final dedup across everything
    deduped, used = deduplicate_sentences(collected, existing_texts=used, similarity_threshold=0.95)
    return deduped, used
