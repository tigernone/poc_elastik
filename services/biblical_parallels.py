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
    "jesus",
    "god",
    "christ",
    "lord",
    "holy spirit",
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
    "hope",
    "mercy",
    "blessing",
    "worship",
    "praise",
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
    prompt = f"""Analyze the following text and extract all Biblical parallels. Provide the output in four sections:

Text to analyze: "{query}"

Bible Stories / Characters – list all people, groups, or stories referenced or implied.
Scripture References – explicit or implicit verse locations (Book Chapter:Verse format).
Biblical Metaphors – symbolic language or imagery that connects to a Biblical narrative.
Keywords – list the key terms, beginning with any Biblical names first.

Rules:
- Exclude generic theological words such as Jesus, God, Christ, Lord, Holy Spirit, love, faith, grace, salvation, redemption, hope, mercy, blessing, worship, praise, and other common devotional terms.
- Only extract items that match the text's context 100%.
- Output must be concise and strictly based on the given text.
- Return ONLY valid JSON with keys: stories_characters, scripture_references, biblical_metaphors, keywords.
- Each item should be 3-10 words maximum.

Output JSON format:
{{
  "stories_characters": ["Canaanite woman (woman who asked for crumbs)", "The Master's table scene"],
  "scripture_references": ["Matthew 15:21-28", "Mark 7:24-30"],
  "biblical_metaphors": ["Crumbs from the Master's table", "Children's bread"],
  "keywords": ["Canaanite woman", "Syrophoenician woman", "Crumbs", "Master's table"]
}}
"""

    logger.info(f"[BiblicalParallels] Analyzing query: {query[:100]}...")
    
    try:
        response = client.chat.completions.create(
            model=settings.CHAT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You extract specific biblical parallels as strict JSON. Be concise, context-accurate, and exclude generic theology terms like Jesus, God, love, faith, grace.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=500,
        )
        raw_content = response.choices[0].message.content.strip()
        logger.info(f"[BiblicalParallels] LLM raw response: {raw_content[:300]}...")
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
    
    logger.info(f"[BiblicalParallels] Extracted - Stories: {result['stories_characters']}, Refs: {result['scripture_references']}, Metaphors: {result['biblical_metaphors']}, Keywords: {result['keywords']}")
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

    Retrieval strategy per your requirements:
    - Stories/Characters: vector search → 5 sentences
    - Scripture References: vector search → 3 sentences  
    - Biblical Metaphors: keyword + vector search → 5 sentences
    - Keywords: keyword search → 2 sentences per keyword
    """
    collected: List[Dict[str, str]] = []
    used: Set[str] = set(existing_texts) if existing_texts else set()

    stories = parallels.get("stories_characters", [])[:5]
    scripture_refs = parallels.get("scripture_references", [])[:4]
    metaphors = parallels.get("biblical_metaphors", [])[:5]
    keywords = parallels.get("keywords", [])[:8]  # Allow more keywords

    logger.info(f"[BiblicalParallels] Gathering sentences - Stories: {stories}, Refs: {scripture_refs}, Metaphors: {metaphors}, Keywords: {keywords}")

    retriever = MultiLevelRetriever(keywords or ([] if base_query is None else base_query.split()))

    def add_vector_items(items: List[str], total_limit: int, label: str):
        """Vector search for items, up to total_limit sentences."""
        count = 0
        for item in items:
            if count >= total_limit:
                break
            remaining = total_limit - count
            hits = get_pure_semantic_search(item, limit=remaining + 2, exclude_texts=used)
            logger.info(f"[BiblicalParallels] Vector search '{item}' → {len(hits)} hits for {label}")
            for hit in hits:
                if count >= total_limit:
                    break
                if is_duplicate(hit["text"], used, similarity_threshold=0.95):
                    continue
                hit["parallels_item"] = item  # Track which item this came from
                collected.append(_tag_sentence(hit, label, is_primary=True))
                used.add(hit["text"])
                count += 1
        logger.info(f"[BiblicalParallels] {label}: collected {count}/{total_limit} sentences")

    def add_keyword_vector_items(items: List[str], total_limit: int, label: str):
        """Keyword + vector hybrid search for items."""
        count = 0
        for item in items:
            if count >= total_limit:
                break
            remaining = total_limit - count
            # Use keyword match with vector scoring
            hits = retriever._text_search(
                query_text=item,
                limit=remaining + 2,
                exclude_texts=used,
                use_vector=True,
                match_type="match",
                require_all_words=False,
            )
            logger.info(f"[BiblicalParallels] Keyword+Vector search '{item}' → {len(hits)} hits for {label}")
            for hit in hits:
                if count >= total_limit:
                    break
                if is_duplicate(hit["text"], used, similarity_threshold=0.95):
                    continue
                hit["parallels_item"] = item
                collected.append(_tag_sentence(hit, label, is_primary=True))
                used.add(hit["text"])
                count += 1
        logger.info(f"[BiblicalParallels] {label}: collected {count}/{total_limit} sentences")

    def add_keyword_items(items: List[str], per_keyword: int, label: str):
        """Keyword search, 2 sentences per keyword."""
        total_count = 0
        for item in items:
            count_for_item = 0
            hits = retriever._text_search(
                query_text=item,
                limit=per_keyword * 3,
                exclude_texts=used,
                use_vector=True,
                match_type="match",
                require_all_words=True,
            )
            logger.info(f"[BiblicalParallels] Keyword search '{item}' → {len(hits)} hits for {label}")
            for hit in hits:
                if is_duplicate(hit["text"], used, similarity_threshold=0.95):
                    continue
                hit["parallels_item"] = item
                collected.append(_tag_sentence(hit, f"{label} ({item})", is_primary=False))
                used.add(hit["text"])
                count_for_item += 1
                total_count += 1
                if count_for_item >= per_keyword:
                    break
        logger.info(f"[BiblicalParallels] {label}: collected {total_count} sentences ({per_keyword} per keyword)")

    # Execute retrieval per section requirements
    add_vector_items(stories, total_limit=5, label="Biblical Stories/Characters")
    add_vector_items(scripture_refs, total_limit=3, label="Scripture References")
    add_keyword_vector_items(metaphors, total_limit=5, label="Biblical Metaphors")
    add_keyword_items(keywords, per_keyword=2, label="Biblical Keywords")

    logger.info(f"[BiblicalParallels] Total collected before dedup: {len(collected)}")

    # Final dedup across everything
    deduped, used = deduplicate_sentences(collected, existing_texts=used, similarity_threshold=0.95)
    
    logger.info(f"[BiblicalParallels] Total after dedup: {len(deduped)}")
    for i, sent in enumerate(deduped[:10]):
        logger.info(f"[BiblicalParallels] #{i+1} [{sent.get('source_type')}] {sent.get('text', '')[:80]}...")
    
    return deduped, used
